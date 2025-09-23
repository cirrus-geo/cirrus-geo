from __future__ import annotations

import json
import logging
import os

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from subprocess import check_call
from time import sleep, time
from typing import IO, Any

import backoff
import boto3

from botocore.exceptions import ClientError

from cirrus.lib.cirrus_payload import CirrusPayload
from cirrus.lib.enums import StateEnum
from cirrus.lib.errors import EventsDisabledError
from cirrus.lib.eventdb import EventDB, daily, hourly
from cirrus.lib.statedb import StateDB, to_current
from cirrus.lib.utils import assume_role, get_client
from cirrus.management.deployment_pointer import DeploymentPointer
from cirrus.management.exceptions import (
    NoExecutionsError,
    PayloadNotFoundError,
    StatsUnavailableError,
)

logger = logging.getLogger(__name__)

DEFAULT_DEPLOYMENTS_DIR_NAME = "deployments"
MAX_SQS_MESSAGE_LENGTH = 2**18  # max length of SQS message
CONFIG_VERSION = 0

WORKFLOW_POLL_INTERVAL = 15  # seconds between state checks


def now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


def _maybe_use_buffer(fileobj: IO) -> IO:
    return fileobj.buffer if hasattr(fileobj, "buffer") else fileobj


class Deployment:
    def __init__(
        self,
        name: str,
        environment: dict,
        session: boto3.Session | None = None,
        iam_role_arn: str | None = None,
        region: str | None = None,
    ) -> None:
        self.name = name
        self.environment = environment
        self._functions: list[str] | None = None
        self.iam_role_arm = iam_role_arn
        self.region = region

        if session is None:
            session = boto3.Session()
        session = assume_role(
            session,
            self.environment.get("CIRRUS_CLI_IAM_ARN", self.iam_role_arm),
            self.environment.get("AWS_REGION", session.region_name),
        )
        self.session = session

    @staticmethod
    def yield_deployments(
        session: boto3.Session,
    ) -> Iterator[str]:
        yield from DeploymentPointer.list_deployments(session=session)

    @classmethod
    def from_pointer(
        cls,
        pointer: DeploymentPointer,
        session: boto3.Session | None,
        iam_role_arn: str | None = None,
    ):
        return cls(
            session=session,
            environment=pointer.get_environment(session=session),
            name=pointer.name,
            iam_role_arn=iam_role_arn,
        )

    @classmethod
    def from_name(
        cls,
        name: str,
        session: boto3.Session,
        iam_role_arn: str | None = None,
    ) -> Deployment:
        dp = DeploymentPointer.get_pointer(name, session=session)
        return cls.from_pointer(dp, session=session, iam_role_arn=iam_role_arn)

    def get_lambda_functions(self, session: boto3.Session | None = None):
        if self._functions is None:
            aws_lambda = get_client("lambda", self.session if self.session else session)

            def deployment_functions_filter(response):
                return [
                    f["FunctionName"].replace(
                        f"{self.environment['CIRRUS_PREFIX']}",
                        "",
                    )
                    for f in response["Functions"]
                    if f["FunctionName"].startswith(self.environment["CIRRUS_PREFIX"])
                ]

            resp = aws_lambda.list_functions()
            self._functions = deployment_functions_filter(resp)
            while "NextMarker" in resp:
                resp = aws_lambda.list_functions(Marker=resp["NextMarker"])
                self._functions += deployment_functions_filter(resp)
        return self._functions

    def exec(self, command, include_user_vars=True, isolated=False):
        import os

        if isolated:
            env = self.environment.copy()
            if include_user_vars:
                env.update(self.user_vars)
            os.execlpe(command[0], *command, env)  # noqa: S606

        os.environ.update(self.environment)
        os.execlp(command[0], *command)  # noqa: S606

    def call(self, command, include_user_vars=True, isolated=False):
        if isolated:
            env = self.environment.copy()
            if include_user_vars:
                env.update(self.user_vars)
            check_call(command, env=env)  # noqa: S603
        else:
            os.environ.update(self.environment)
            check_call(command)  # noqa: S603

    def get_payload_state(self, payload_id):
        from cirrus.lib.statedb import StateDB

        statedb = StateDB(
            table_name=self.environment["CIRRUS_STATE_DB"],
            session=self.session,
        )

        @backoff.on_predicate(backoff.expo, lambda x: x is None, max_time=60)
        def _get_payload_item_from_statedb(statedb, payload_id):
            return statedb.get_dbitem(payload_id)

        state = _get_payload_item_from_statedb(statedb, payload_id)

        if not state:
            raise PayloadNotFoundError(payload_id)
        return state

    def enqueue_payload(self, payload):
        stream = None

        if hasattr(payload, "read"):
            stream = _maybe_use_buffer(payload)
            # add two to account for EOF and needing to know
            # if greater than not just equal to max length
            payload = payload.read(MAX_SQS_MESSAGE_LENGTH + 2)

        if len(payload.encode("utf-8")) > MAX_SQS_MESSAGE_LENGTH:
            import uuid

            stream.seek(0)
            bucket = self.environment["CIRRUS_PAYLOAD_BUCKET"]
            key = f"payloads/{uuid.uuid1()}.json"
            url = f"s3://{bucket}/{key}"
            logger.warning("Message exceeds SQS max length.")
            logger.warning("Uploading to '%s'", url)
            s3 = get_client(
                "s3",
                session=self.session,
            )
            s3.upload_fileobj(stream, bucket, key)
            payload = json.dumps({"url": url})

        sqs = get_client(
            "sqs",
            session=self.session,
        )
        return sqs.send_message(
            QueueUrl=self.environment["CIRRUS_PROCESS_QUEUE_URL"],
            MessageBody=payload,
        )

    def get_payload_by_id(self, payload_id, output_fileobj):
        from cirrus.lib.statedb import StateDB

        # TODO: error handling
        bucket, key = StateDB.payload_id_to_bucket_key(
            payload_id,
            payload_bucket=self.environment["CIRRUS_PAYLOAD_BUCKET"],
        )
        logger.debug("bucket: '%s', key: '%s'", bucket, key)

        s3 = get_client(
            "s3",
            session=self.session,
        )

        return s3.download_fileobj(bucket, key, output_fileobj)

    def get_execution(self, arn):
        sfn = get_client(
            "stepfunctions",
            session=self.session,
        )
        return sfn.describe_execution(executionArn=arn)

    def get_execution_by_payload_id(self, payload_id):
        execs = self.get_payload_state(payload_id).get("executions", [])
        try:
            exec_arn = execs[-1]
        except IndexError as e:
            raise NoExecutionsError(payload_id) from e

        return self.get_execution(exec_arn)

    def invoke_lambda(
        self,
        event: str,
        function_name: str,
        session: boto3.Session = None,
    ):
        aws_lambda = get_client(
            "lambda",
            session=self.session if self.session else session,
        )
        if function_name not in self.get_lambda_functions():
            raise ValueError(
                f"lambda named '{function_name}' not found in deployment '{self.name}'",
            )
        full_name = f"{self.environment['CIRRUS_PREFIX']}{function_name}"
        response = aws_lambda.invoke(FunctionName=full_name, Payload=event)
        if response["StatusCode"] < 200 or response["StatusCode"] > 299:
            raise RuntimeError(response)

        return json.load(response["Payload"])

    def run_workflow(
        self,
        payload: dict,
        timeout: int = 3600,
        poll_interval: int = WORKFLOW_POLL_INTERVAL,
    ) -> dict[str, Any]:
        """

        Args:
            deployment (Deployment): where the workflow will be run.

            payload (str): payload to pass to the deployment to kick off the workflow.

            timeout (Optional[int]): - upper bound on the number of seconds to poll the
                                       deployment before considering the test failed.

            poll_interval (Optional[int]): - seconds to delay between checks of the
                                             workflow status.

        Returns:
            dict containing output payload or error message

        """
        input = CirrusPayload(payload)
        input.validate()
        wf_id = input["id"]
        logger.info("Submitting %s to %s", wf_id, self.name)
        resp = self.enqueue_payload(json.dumps(input))
        logger.debug(resp)

        state = "PROCESSING"
        end_time = time() + timeout - poll_interval
        while state == "PROCESSING" and time() < end_time:
            sleep(poll_interval)
            resp = self.get_payload_state(wf_id)
            state = resp["state_updated"].split("_")[0]
            logger.debug({"state": state})

        execution = self.get_execution_by_payload_id(wf_id)

        output: dict[str, Any]
        if state == "COMPLETED":
            output = CirrusPayload.from_event(json.loads(execution["output"]))
        elif state == "PROCESSING":
            output = {"last_error": "Unkonwn: cirrus-mgmt polling timeout exceeded"}
        else:
            output = {"last_error": resp.get("last_error", "last error not recorded")}

        return output

    def template_payload(
        self,
        payload: str,
        additional_vars: dict[str, str] | None = None,
        silence_templating_errors: bool = False,
        include_user_vars: bool = True,
    ):
        from .utils.templating import template_payload

        _vars = self.environment.copy()

        return template_payload(
            payload,
            _vars,
            silence_templating_errors,
            **(additional_vars or {}),
        )

    def yield_payloads(
        self,
        collections_workflow: str,
        limit: int | None,
        query_args: dict[str, Any],
        rerun: bool,
    ) -> Iterator[dict]:
        statedb = StateDB(table_name=self.environment["CIRRUS_STATE_DB"])

        for item in statedb.get_items(
            collections_workflow=collections_workflow,
            limit=limit,
            **query_args,
        ):
            payload = self.fetch_payload(item["payload_id"], rerun)
            if payload:
                yield payload

    def fetch_payload(self, payload_id: str, rerun: bool | None = None):
        with BytesIO() as b:
            try:
                self.get_payload_by_id(payload_id, b)
                b.seek(0)
                payload = json.load(b)
                if rerun:
                    payload["process"][0]["replace"] = True
                return payload

            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    logger.error(
                        "Payload ID: '%s' was not found in S3",
                        payload_id,
                    )
                else:
                    logger.error(
                        "Error retrieving payload ID '%s': '%s'",
                        payload_id,
                        e,
                    )

    def get_workflow_summary(
        self,
        collections: str,
        workflow_name: str,
        since: timedelta | None = None,
        limit: int = 10000,
    ) -> dict[str, Any]:
        "Get item counts by state for a collections/workflow from DynamoDB"
        statedb = StateDB(
            table_name=self.environment["CIRRUS_STATE_DB"],
            session=self.session,
        )
        collections_workflow = f"{collections}_{workflow_name}"
        logger.debug("Getting summary for %s", collections_workflow)
        counts = {}
        for s in StateEnum:
            counts[s.value] = statedb.get_counts(
                collections_workflow,
                limit=limit,
                state=s,
                since=since,
            )
        return {
            "collections": collections,
            "workflow": workflow_name,
            "counts": counts,
        }

    def get_workflow_stats(
        self,
    ) -> dict[str, Any] | None:
        "Get aggregate workflow state transition stats from Timestream"
        eventdb = EventDB(self.environment["CIRRUS_EVENT_DB_AND_TABLE"])
        logger.debug("Getting stats")
        try:
            return {
                "state_transitions": {
                    "daily": daily(eventdb.query_by_bin_and_duration("1d", "60d")),
                    "hourly": hourly(eventdb.query_by_bin_and_duration("1h", "36h")),
                    "hourly_rolling": hourly(
                        eventdb.query_hour(1, 0),
                        eventdb.query_hour(2, 1),
                    ),
                },
            }
        except EventsDisabledError as e:
            raise StatsUnavailableError from e

    def get_workflow_items(
        self,
        collections: str,
        workflow_name: str,
        state: str | None = None,
        since: timedelta | None = None,
        limit: int = 10,
        nextkey: str | None = None,
        sort_ascending: bool = False,
        sort_index: str = "updated",
    ) -> dict[str, Any]:
        "Get items for a collections/workflow from DynamoDB"
        statedb = StateDB(
            table_name=self.environment["CIRRUS_STATE_DB"],
            session=self.session,
        )
        collections_workflow = f"{collections}_{workflow_name}"
        logger.debug("Getting items for %s", collections_workflow)
        items_page = statedb.get_items_page(
            collections_workflow=collections_workflow,
            limit=limit,
            nextkey=nextkey,
            state=state,
            since=since,
            sort_ascending=sort_ascending,
            sort_index=sort_index,
        )
        return {"items": [to_current(item) for item in items_page["items"]]}

    def get_workflow_item(
        self,
        collections: str,
        workflow_name: str,
        itemids: str,
    ) -> dict[str, Any]:
        "Get individual item for a collections/workflow from DynamoDB"
        statedb = StateDB(
            table_name=self.environment["CIRRUS_STATE_DB"],
            session=self.session,
        )
        payload_id = f"{collections}/workflow-{workflow_name}/{itemids}"
        item = statedb.dbitem_to_item(statedb.get_dbitem(payload_id))
        return {"item": to_current(item)}
