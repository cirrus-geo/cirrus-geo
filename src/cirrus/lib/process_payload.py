from __future__ import annotations

import contextlib
import json
import logging
import os
import uuid

from copy import deepcopy
from typing import Self

import jsonpath_ng.ext as jsonpath

from boto3utils import s3
from botocore.exceptions import ClientError

from cirrus.lib.enums import StateEnum
from cirrus.lib.errors import NoUrlError
from cirrus.lib.events import WorkflowEventManager
from cirrus.lib.logging import get_task_logger
from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import extract_event_records, get_client, payload_from_s3

logger = logging.getLogger(__name__)

MAX_PAYLOAD_LENGTH = 250000


class TerminalError(Exception):
    pass


class ProcessPayload(dict):
    def __init__(self, *args, set_id_if_missing=False, state_item=None, **kwargs):
        """Initialize a ProcessPayload, verify required fields, and assign an ID

        Args:
            state_item (Dict, optional): Dictionary of entry in StateDB.
                Defaults to None.
        """
        super().__init__(*args, **kwargs)

        self.logger = get_task_logger(__name__, payload=self)

        if "process" not in self:
            raise ValueError(
                "ProcessPayload must have a `process` array of process definintions",
            )

        if not isinstance(self["process"], list) or len(self["process"]) == 0:
            raise TypeError(
                "ProcessPayload `process` must be an array "
                "with at least one process definition",
            )

        self.process = self["process"][0]

        self.features = self.get("features", [])

        if "id" not in self and set_id_if_missing:
            self.set_id()

        if "upload_options" not in self.process:
            raise ValueError(
                "ProcessPayload.process must have `upload_options` defined",
            )

        if "workflow" not in self.process:
            raise ValueError(
                "ProcessPayload.process must have `workflow` specifying workflow name",
            )

        if "tasks" not in self.process:
            raise ValueError("ProcessPayload.process must have `tasks` defined")

        self.tasks = self.process["tasks"]

        if "workflow-" not in self["id"]:
            raise ValueError(f'Invalid payload id: {self["id"]}')

        for item in self.features:
            if "links" not in item:
                item["links"] = []

        self.state_item = state_item

    @classmethod
    def from_event(cls, event: dict, **kwargs) -> ProcessPayload:
        """Parse a Cirrus event and return a ProcessPayload instance

        Args:
            event (Dict): An event from SNS, SQS, or containing an s3 URL to payload

        Returns:
            ProcessPayload: A ProcessPayload instance
        """
        records = list(extract_event_records(event))

        if len(records) == 0:
            raise ValueError("Failed to extract record: %s", json.dumps(event))
        if len(records) > 1:
            raise ValueError("Multiple payloads are not supported")

        payload = records[0]

        # if the payload has a URL in it then we'll fetch it from S3
        with contextlib.suppress(NoUrlError):
            payload = payload_from_s3(payload)

        return cls(payload, **kwargs)

    def next_payloads(self):
        if len(self["process"]) <= 1:
            return None
        next_processes = (
            [self["process"][1]]
            if isinstance(self["process"][1], dict)
            else self["process"][1]
        )
        for process in next_processes:
            new = deepcopy(self)
            del new["id"]
            new["process"].pop(0)
            new["process"][0] = process
            if "chain_filter" in process:
                jsonfilter = jsonpath.parse(
                    f'$.features[?({process["chain_filter"]})]',
                )
                new["features"] = [match.value for match in jsonfilter.find(new)]
            yield new

    def set_id(self):
        if "id" in self:
            return

        if not self.features:
            raise ValueError(
                "ProcessPayload has no `id` specified and one "
                "cannot be constructed without `features`.",
            )

        if "collections" in self.process:
            # allow overriding of collections name
            collections_str = self.process["collections"]
        else:
            # otherwise, get from items
            cols = sorted(
                {i["collection"] for i in self.features if "collection" in i},
            )
            collections_str = "/".join(cols) if len(cols) != 0 else "none"

        items_str = "/".join(sorted([i["id"] for i in self.features]))
        self["id"] = (
            f"{collections_str}/workflow-{self.process['workflow']}/{items_str}"
        )

    @staticmethod
    def upload_to_s3(payload: dict, bucket: str | None = None) -> str:
        """Helper function to upload a dict (not necessarily a ProcessPayload) to s3"""
        # url-payloads do not need to be re-uploaded
        if "url" in payload:
            return payload["url"]
        if bucket is None:
            bucket = os.environ["CIRRUS_PAYLOAD_BUCKET"]
        url = f"s3://{bucket}/payloads/{uuid.uuid1()}.json"
        s3().upload_json(payload, url)
        return url

    def get_payload(self) -> dict:
        """Get original payload for this ProcessPayload

        Returns:
            Dict: Cirrus Input ProcessPayload
        """
        payload_length = len(json.dumps(self).encode())
        if payload_length <= MAX_PAYLOAD_LENGTH:
            return dict(self)

        payload_bucket = os.getenv("CIRRUS_PAYLOAD_BUCKET", None)
        if not payload_bucket:
            raise RuntimeError(
                "No payload bucket defined and payload too large: "
                f"length {payload_length} (max {MAX_PAYLOAD_LENGTH}). "
                "To enable uploads oversized payloads define `CIRRUS_PAYLOAD_BUCKET`.",
            )

        url = self.upload_to_s3(self, payload_bucket)
        return {"url": url}

    def __call__(self, wfem) -> str | None:
        """Add this ProcessPayload to Cirrus and start workflow

        Returns:
            str: ProcessPayload ID
        """
        payload_bucket = os.getenv("CIRRUS_PAYLOAD_BUCKET", None)

        if not payload_bucket:
            raise ValueError("env var CIRRUS_PAYLOAD_BUCKET must be defined")

        arn = os.getenv("CIRRUS_BASE_WORKFLOW_ARN") + self.process["workflow"]
        url = f"s3://{payload_bucket}/{self['id']}/input.json"

        # start workflow
        try:
            # add input payload to s3
            s3().upload_json(self, url)

            # create DynamoDB record
            # -> this overwrites existing states other than PROCESSING and CLAIMED
            execution_name = wfem.claim_processing(
                self["id"],
                payload_url=url,
                arn_base=arn,
            )

            # invoke step function
            self.logger.debug("Running Step Function %s", arn)
            get_client("stepfunctions").start_execution(
                stateMachineArn=arn,
                name=execution_name,
                input=json.dumps(self.get_payload()),
            )

            # add execution to DynamoDB record
            wfem.started_processing(
                self["id"],
                f"{arn}:{execution_name}",
                payload_url=url,
            )

            return self["id"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # TODO: may need to address this check for claim and processing
                #       separately now that we are specifying the execution name
                wfem.skipping(self["id"], state=StateEnum.PROCESSING, payload_url=url)
                return None
            if e.response["Error"]["Code"] == "StateMachineDoesNotExist":
                # This failure is tracked in the DB and we raise an error
                # so we can handle it specifically, to keep the payload
                # falling through to the DLQ and alerting.
                logger.error(e)
                wfem.failed(self["id"], str(e), payload_url=url)
                raise TerminalError() from e
            raise
        except Exception as e:
            # This case should be like the above, except we don't know
            # why it happened. We'll be conservative and not raise a
            # terminal failure, so it will get retried in case it was
            # a transient failure. If we find terminal failures handled
            # here, we should add terminal exception handlers for them.
            msg = f"failed starting workflow ({e})"
            self.logger.exception(msg)
            wfem.failed(self.get("id", "missing"), msg, payload_url=url)
            raise


class ProcessPayloads:
    def __init__(
        self: Self,
        process_payloads: list[ProcessPayload],
        statedb: StateDB,
        state_items=None,
    ) -> None:
        self.payloads = process_payloads
        self.statedb = statedb
        if state_items and len(state_items) != len(self.payloads):
            raise ValueError(
                "The number of state items does not match the number of payloads: "
                f"{len(state_items)} != {len(self.payloads)}.",
            )
        self.state_items = state_items

    def __getitem__(self, index):
        return self.payloads[index]

    @property
    def payload_ids(self) -> list[str]:
        """Return list of Payload IDs

        Returns:
            List[str]: List of Payload IDs
        """
        return [c["id"] for c in self.payloads]

    def get_states(self) -> dict[str, StateEnum]:
        if self.state_items is None:
            items = [
                self.statedb.dbitem_to_item(i)
                for i in self.statedb.get_dbitems(self.payload_ids)
            ]
            self.state_items = items
        return {c["payload_id"]: StateEnum(c["state"]) for c in self.state_items}

    def process(
        self: Self,
        wfem: WorkflowEventManager,
        replace: bool = False,
    ) -> dict[str, list[str]]:
        """Create Item in Cirrus State DB for each ProcessPayload and add to
        processing queue"""
        payload_ids: dict[str, list[str]] = {
            "started": [],
            "skipped": [],
            "dropped": [],
            "failed": [],
        }
        # check existing states
        states = self.get_states()

        for payload in self.payloads:
            _replace = replace or payload.process.get("replace", False)

            # check existing state for Item, if any
            state = states.get(payload["id"])

            if (
                payload["id"] in payload_ids["started"]
                or payload["id"] in payload_ids["skipped"]
                or payload["id"] in payload_ids["failed"]
            ):
                logger.warning("Dropping duplicated payload %s", payload["id"])
                wfem.duplicated(
                    payload["id"],
                    payload_url=StateDB.payload_id_to_url(payload["id"]),
                )
                payload_ids["dropped"].append(payload["id"])
            elif (
                state == StateEnum.FAILED
                or state == StateEnum.ABORTED
                or state is None
                or _replace
            ):
                try:
                    payload_id = payload(wfem)
                except TerminalError:
                    payload_ids["failed"].append(payload["id"])
                else:
                    if payload_id is not None:
                        payload_ids["started"].append(payload_id)
                    else:
                        payload_ids["skipped"].append(payload["id"])
            else:
                logger.info(
                    "Skipping %s, input already in %s state",
                    payload["id"],
                    state,
                )
                wfem.skipping(
                    payload["id"],
                    state,
                    payload_url=StateDB.payload_id_to_url(payload["id"]),
                )
                payload_ids["skipped"].append(payload["id"])
                continue

        return payload_ids
