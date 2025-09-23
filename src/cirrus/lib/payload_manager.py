from __future__ import annotations

import json
import logging
import os
import uuid

from copy import deepcopy
from typing import Self

import jsonpath_ng.ext as jsonpath

from boto3utils import s3
from botocore.exceptions import ClientError

from cirrus.lib.cirrus_payload import CirrusPayload
from cirrus.lib.enums import StateEnum
from cirrus.lib.events import WorkflowEventManager
from cirrus.lib.logging import get_task_logger
from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import (
    SNSMessage,
    build_item_sns_attributes,
    get_client,
)

logger = logging.getLogger(__name__)

MAX_PAYLOAD_LENGTH = 250000


class TerminalError(Exception):
    pass


class PayloadManager:
    def __init__(
        self,
        *args,
        set_id_if_missing: bool = False,
        state_item: dict | None = None,
        **kwargs,
    ):
        """Create a PayloadManager wrapper around a CirrusPayload.

        All positional and keyword arguments (other than set_id_if_missing and
        state_item) are forwarded directly to CirrusPayload. After construction
        the payload is validated, a task-scoped logger is created, and (optionally)
        an existing StateDB item is attached for downstream state handling.

        Args:
            *args: Positional arguments passed through to CirrusPayload (typically
                a single payload dict).
            set_id_if_missing (bool): If True, generate and assign an ID when the
                incoming payload lacks one.
            state_item (dict | None): Existing StateDB record for this payload, if
                already persisted.
            **kwargs: Additional keyword arguments forwarded to CirrusPayload.

        Raises:
            Exception: Propagates any validation or construction errors raised by
                CirrusPayload.validate().
        """
        self.payload = CirrusPayload(
            *args,
            set_id_if_missing=set_id_if_missing,
            **kwargs,
        )
        self.payload.validate()

        self.logger = get_task_logger(__name__, payload=self.payload)
        self.state_item = state_item

    def next_payloads(self):
        if len(self.payload["process"]) <= 1:
            return None
        next_processes = (
            [self.payload["process"][1]]
            if isinstance(self.payload["process"][1], dict)
            else self.payload["process"][1]
        )
        for process in next_processes:
            new = deepcopy(self.payload)
            del new["id"]
            new["process"].pop(0)
            new["process"][0] = process
            if "chain_filter" in process:
                jsonfilter = jsonpath.parse(
                    f"$.features[?({process['chain_filter']})]",
                )
                new["features"] = [match.value for match in jsonfilter.find(new)]
            yield new

    @staticmethod
    def upload_to_s3(payload: dict, bucket: str | None = None) -> str:
        """Helper function to upload a dict (not necessarily a payload) to s3"""
        # url-payloads do not need to be re-uploaded
        if "url" in payload:
            return payload["url"]
        if bucket is None:
            bucket = os.environ["CIRRUS_PAYLOAD_BUCKET"]
        url = f"s3://{bucket}/payloads/{uuid.uuid1()}.json"
        s3().upload_json(payload, url)
        return url

    def get_payload(self) -> dict:
        """Get original payload for this PayloadManager

        Returns:
            Dict: Input payload
        """
        payload_length = len(json.dumps(self.payload).encode())
        if payload_length <= MAX_PAYLOAD_LENGTH:
            return dict(self.payload)

        payload_bucket = os.getenv("CIRRUS_PAYLOAD_BUCKET", None)
        if not payload_bucket:
            raise RuntimeError(
                "No payload bucket defined and payload too large: "
                f"length {payload_length} (max {MAX_PAYLOAD_LENGTH}). "
                "To enable uploads oversized payloads define `CIRRUS_PAYLOAD_BUCKET`.",
            )

        url = self.upload_to_s3(self.payload, payload_bucket)
        return {"url": url}

    def items_to_sns_messages(self: Self) -> list[SNSMessage]:
        """Prepare list of Payload Items as SNS Messages for publishing"""
        return [
            SNSMessage(
                body=json.dumps(item),
                attributes=build_item_sns_attributes(item),
            )
            for item in self.payload.items_as_dicts
        ]

    def _fail_and_raise(self, wfem, e, url):
        """
        This function is to handle exceptions that we don't know why they
        happened. We'll be conservative, log+raise. Not raise a terminal failure, so it
        will get retried in case it was a transient failure. If we find terminal
        failures handled here, we should add terminal exception handlers for them.
        """
        msg = f"failed starting workflow ({e})"
        self.logger.exception(msg)
        wfem.failed(self.payload.get("id", "missing"), msg, payload_url=url)
        raise

    def _claim(
        self,
        wfem: WorkflowEventManager,
        execution_arn: str,
        previous_state: StateEnum,
    ) -> tuple[str, str, str]:
        """Claim this PayloadManager's payload, and return
        (state_machine_arn, execution_name, url)
        to be used for uploading and invoking the state machine"""

        payload_bucket = os.getenv("CIRRUS_PAYLOAD_BUCKET", None)

        if not payload_bucket:
            raise ValueError("env var CIRRUS_PAYLOAD_BUCKET must be defined")

        (
            state_machine_arn,
            execution_name,
        ) = PayloadManagers.get_state_machine_arn_and_execution_name(execution_arn)
        url = f"s3://{payload_bucket}/{self.payload['id']}/input.json"

        # claim workflow
        try:
            # create or update DynamoDB record
            # -> overwrites states other than PROCESSING and CLAIMED
            wfem.claim_processing(
                self.payload["id"],
                payload_url=url,
                execution_arn=execution_arn,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # conditional errors on state being CLAIMED or PROCESSING.
                # if PROCESSING, skip w/o need for other action, and return None
                # if CLAIMED, check if state_machine_arn and execution_name (uuid) are
                # equal to above, warn if different, and reguardless, update for this
                # function to use the pair from the database.
                db_state = (
                    StateEnum(
                        e.response["Item"]["state_updated"]["S"].split("_")[0],
                    )
                    if "Item" in e.response
                    else StateEnum.PROCESSING
                )

                if db_state is StateEnum.CLAIMED:
                    db_exec = e.response["Item"]["executions"]["L"][0]["S"].split("_")[
                        0
                    ]
                    if db_exec != execution_arn:
                        self.logger.warning(
                            msg="payload found in CLAIMED",
                            extra={
                                "payload_id": self.payload["id"],
                                "db_exec_arn": db_exec,
                                "planned_exec_arn": execution_arn,
                            },
                        )
                        (
                            state_machine_arn,
                            execution_name,
                        ) = PayloadManagers.get_state_machine_arn_and_execution_name(
                            db_exec,
                        )
                else:
                    wfem.skipping(
                        self.payload["id"],
                        state=db_state,
                        payload_url=url,
                        message=f"state before claim attempt was {previous_state}",
                    )
                    return "", "", ""
            else:
                # unknown ClientError
                self._fail_and_raise(wfem, e, url)
        return state_machine_arn, execution_name, url

    def __call__(
        self,
        wfem,
        execution_arn,
        previous_state,
    ) -> str | None:
        """Add this PayloadManager's payload to Cirrus and start workflow

        Returns:
            str: Payload ID
        """

        state_machine_arn, execution_name, url = self._claim(
            wfem,
            execution_arn,
            previous_state,
        )

        if state_machine_arn == "":
            # skipped with likely already PROCESSING (announced from _claim function)
            return None

        try:
            # add input payload to s3
            s3().upload_json(self.payload, url)
        except Exception as e:  # noqa: BLE001
            self._fail_and_raise(wfem, e, url)

        # invoke step function
        self.logger.debug("Running Step Function %s", execution_arn)
        started_sfn = False
        try:
            get_client("stepfunctions").start_execution(
                stateMachineArn=state_machine_arn,
                name=execution_name,
                input=json.dumps(self.get_payload()),
            )
            started_sfn = True
        except ClientError as e:
            if e.response["Error"]["Code"] == "StateMachineDoesNotExist":
                # This failure is tracked in the DB and we raise an error
                # so we can handle it specifically, to keep the payload
                # falling through to the DLQ and alerting.
                logger.error(e)
                wfem.failed(self.payload["id"], str(e), payload_url=url)
                raise TerminalError() from e
            if e.response["Error"]["Code"] != "ExecutionAlreadyExists":
                self._fail_and_raise(wfem, e, url)
            # Let ExecutionAlreadyExists pass, to try setting PROCESSING

        try:
            wfem.started_processing(
                self.payload["id"],
                execution_arn=execution_arn,
                payload_url=url,
            )
        except ClientError as e:
            if (
                e.response["Error"]["Code"] == "ConditionalCheckFailedException"
                and "Item" in e.response
            ):
                db_state = StateEnum(
                    e.response["Item"]["state_updated"]["S"].split("_")[0],
                )
                wfem.skipping(
                    self.payload["id"],
                    state=db_state,
                    payload_url=url,
                    message=(
                        "started stepfunction, but could not set processing "
                        if started_sfn
                        else (
                            "stepfunction started by another process, "
                            "and database already updated "
                        )
                    )
                    + f"({db_state}).",
                )
                return None
            self._fail_and_raise(wfem, e, url)
        return self.payload["id"]


class PayloadManagers:
    def __init__(
        self: Self,
        payload_managers: list[PayloadManager],
        statedb: StateDB,
        state_items: list[dict] | None = None,
    ) -> None:
        self.payload_managers = payload_managers
        self.statedb = statedb
        if state_items and len(state_items) != len(self.payload_managers):
            raise ValueError(
                "The number of state items does not match the number of payloads: "
                f"{len(state_items)} != {len(self.payload_managers)}.",
            )
        self.state_items = state_items

    def __getitem__(self, index):
        return self.payload_managers[index]

    @property
    def payload_ids(self) -> list[str]:
        """Return list of Payload IDs

        Returns:
            List[str]: List of Payload IDs
        """
        return [c.payload["id"] for c in self.payload_managers]

    def get_states_and_exec_arn(self) -> dict[str, tuple]:
        if self.state_items is None:
            items = [
                self.statedb.dbitem_to_item(i)
                for i in self.statedb.get_dbitems(self.payload_ids)
            ]
            self.state_items = items
        response = dict(self.get_process_attrs(self.state_items))
        response.update(
            {
                p.payload["id"]: (
                    None,
                    self.gen_execution_arn(
                        p.payload["id"],
                        p.payload.process_definition["workflow"],
                    ),
                )
                for p in self.payload_managers
                if p.payload["id"] not in response
            },
        )
        return response

    @staticmethod
    def get_process_attrs(state_items):
        for si in state_items:
            payload_id = si["payload_id"]
            state = StateEnum(si["state"]) if si["state"] is not None else None

            # if workflow is found in CLAIMED state, then we want the last execution to
            # determine where in the process of sfn execution the failure to proceeed to
            # PROCESSING occurred.
            if state == StateEnum.CLAIMED:
                exec_arn = si["executions"][-1].rpartition("/")[2]
            else:
                exec_arn = PayloadManagers.gen_execution_arn(
                    payload_id,
                    si["workflow"],
                    si.get("executions"),
                )

            yield payload_id, (state, exec_arn)

    @staticmethod
    def gen_execution_arn(payload_id, workflow, executions=None) -> str:
        """
        Generate an execution arn for the given payload_id, using the state_item info if
        given.
        """
        if executions is None:
            executions = []
        execution_name = uuid.uuid5(uuid.NAMESPACE_URL, f"{payload_id}/{executions}")
        workflow_execution_base = os.environ["CIRRUS_BASE_WORKFLOW_ARN"].replace(
            ":stateMachine:",
            ":execution:",
        )
        return f"{workflow_execution_base}{workflow}:{execution_name}"

    @staticmethod
    def get_state_machine_arn_and_execution_name(execution_arn: str) -> tuple[str, str]:
        base_execution_arn, _, execution_name = execution_arn.rpartition(":")

        return base_execution_arn.replace(
            ":execution:",
            ":stateMachine:",
        ), execution_name

    def process(
        self: Self,
        wfem: WorkflowEventManager,
        replace: bool = False,
    ) -> dict[str, list[str]]:
        """Create Item in Cirrus State DB for each PayloadManager's payload and add to
        processing queue"""
        payload_ids: dict[str, list[str]] = {
            "started": [],
            "skipped": [],
            "dropped": [],
            "failed": [],
        }
        # check existing states
        states = self.get_states_and_exec_arn()

        for payload_manager in self.payload_managers:
            _replace = replace or payload_manager.payload.process_definition.get(
                "replace",
                False,
            )

            # check existing state for Item, if any
            state, exec_arn = states[payload_manager.payload["id"]]

            if (
                payload_manager.payload["id"] in payload_ids["started"]
                or payload_manager.payload["id"] in payload_ids["skipped"]
                or payload_manager.payload["id"] in payload_ids["failed"]
            ):
                logger.warning(
                    "Dropping duplicated payload %s",
                    payload_manager.payload["id"],
                )
                wfem.duplicated(
                    payload_manager.payload["id"],
                    payload_url=StateDB.payload_id_to_url(
                        payload_manager.payload["id"],
                    ),
                )
                payload_ids["dropped"].append(payload_manager.payload["id"])
            elif (
                state in (StateEnum.FAILED, StateEnum.ABORTED, StateEnum.CLAIMED, None)
                or _replace
            ):
                try:
                    payload_id = payload_manager(wfem, exec_arn, state)
                except TerminalError:
                    payload_ids["failed"].append(payload_manager.payload["id"])
                else:
                    if payload_id is not None:
                        payload_ids["started"].append(payload_id)
                    else:
                        payload_ids["skipped"].append(payload_manager.payload["id"])
            else:
                logger.info(
                    "Skipping %s, input already in %s state",
                    payload_manager.payload["id"],
                    state,
                )
                wfem.skipping(
                    payload_id=payload_manager.payload["id"],
                    state=state,
                    payload_url=StateDB.payload_id_to_url(
                        payload_manager.payload["id"],
                    ),
                )
                payload_ids["skipped"].append(payload_manager.payload["id"])
                continue

        return payload_ids
