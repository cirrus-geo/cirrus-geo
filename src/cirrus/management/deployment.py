from __future__ import annotations

import dataclasses
import json
import logging
import os

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from subprocess import check_call
from time import sleep, time
from typing import IO, Any

import backoff
import boto3

from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.utils import get_client
from cirrus.management import exceptions
from cirrus.management.deployment_pointer import DeploymentPointer

logger = logging.getLogger(__name__)

DEFAULT_DEPLOYMENTS_DIR_NAME = "deployments"
MAX_SQS_MESSAGE_LENGTH = 2**18  # max length of SQS message
CONFIG_VERSION = 0

WORKFLOW_POLL_INTERVAL = 15  # seconds between state checks


def now_isoformat():
    return datetime.now(UTC).isoformat()


def _maybe_use_buffer(fileobj: IO):
    return fileobj.buffer if hasattr(fileobj, "buffer") else fileobj


@dataclasses.dataclass
class DeploymentMeta:
    name: str
    created: str
    updated: str
    stackname: str
    profile: str
    environment: dict
    user_vars: dict
    config_version: int

    def save(self, path: Path) -> int:
        return path.write_text(self.asjson(indent=4))

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def asjson(self, *args, **kwargs) -> str:
        return json.dumps(self.asdict(), *args, **kwargs)


@dataclasses.dataclass
class Deployment(DeploymentMeta):
    def __init__(
        self,
        *args,
        session: boto3.Session | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.session = session if session else boto3.Session()
        self._functions: list[str] | None = None

    @staticmethod
    def yield_deployments(
        region: str | None = None,
        session: boto3.Session | None = None,
    ) -> Iterator[DeploymentPointer]:
        yield from DeploymentPointer.list(region=region, session=session)

    @classmethod
    def from_pointer(
        cls,
        pointer: DeploymentPointer,
        session: boto3.Session | None = None,
    ) -> Deployment:
        return cls(session=session, **pointer.get_config(session=session))

    @classmethod
    def from_name(cls, name: str, session: boto3.Session | None = None) -> Deployment:
        dp = DeploymentPointer.get(name, session=session)
        return cls.from_pointer(dp, session=session)

    def get_lambda_functions(self):
        if self._functions is None:
            aws_lambda = get_client("lambda")

            def deployment_functions_filter(response):
                return [
                    f["FunctionName"].replace(f"{self.stackname}-", "")
                    for f in response["Functions"]
                    if f["FunctionName"].startswith(self.stackname)
                ]

            resp = aws_lambda.list_functions()
            self._functions = deployment_functions_filter(resp)
            while "NextMarker" in resp:
                resp = aws_lambda.list_functions(Marker=resp["NextMarker"])
                self._functions += deployment_functions_filter(resp)
        return self._functions

    def set_env(self, include_user_vars=False):
        os.environ.update(self.environment)
        if include_user_vars:
            os.environ.update(self.user_vars)
        if self.profile:
            os.environ["AWS_PROFILE"] = self.profile

    def exec(self, command, include_user_vars=True, isolated=False):
        import os

        if isolated:
            env = self.environment.copy()
            if include_user_vars:
                env.update(self.user_vars)
            os.execlpe(command[0], *command, env)  # noqa: S606

        self.set_env(include_user_vars=include_user_vars)
        os.execlp(command[0], *command)  # noqa: S606

    def call(self, command, include_user_vars=True, isolated=False):
        if isolated:
            env = self.environment.copy()
            if include_user_vars:
                env.update(self.user_vars)
            check_call(command, env=env)  # noqa: S603
        else:
            self.set_env(include_user_vars=include_user_vars)
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
            raise exceptions.PayloadNotFoundError(payload_id)
        return state

    def process_payload(self, payload):
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
            s3 = get_client("s3", session=self.session)
            s3.upload_fileobj(stream, bucket, key)
            payload = json.dumps({"url": url})

        sqs = get_client("sqs", session=self.session)
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

        s3 = get_client("s3", session=self.session)

        return s3.download_fileobj(bucket, key, output_fileobj)

    def get_execution(self, arn):
        sfn = get_client("stepfunctions", session=self.session)
        return sfn.describe_execution(executionArn=arn)

    def get_execution_by_payload_id(self, payload_id):
        execs = self.get_payload_state(payload_id).get("executions", [])
        try:
            exec_arn = execs[-1]
        except IndexError as e:
            raise exceptions.NoExecutionsError(payload_id) from e

        return self.get_execution(exec_arn)

    def invoke_lambda(self, event, function_name):
        aws_lambda = get_client("lambda", session=self.session)
        if function_name not in self.get_lambda_functions():
            raise ValueError(
                f"lambda named '{function_name}' not found in deployment '{self.name}'",
            )
        full_name = f"{self.stackname}-{function_name}"
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
        payload = ProcessPayload(payload)
        wf_id = payload["id"]
        logger.info("Submitting %s to %s", wf_id, self.name)
        resp = self.process_payload(json.dumps(payload))
        logger.debug(resp)

        state = "PROCESSING"
        end_time = time() + timeout - poll_interval
        while state == "PROCESSING" and time() < end_time:
            sleep(poll_interval)
            resp = self.get_payload_state(wf_id)
            state = resp["state_updated"].split("_")[0]
            logger.debug({"state": state})

        execution = self.get_execution_by_payload_id(wf_id)

        if state == "COMPLETED":
            output = dict(ProcessPayload.from_event(json.loads(execution["output"])))
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
        if include_user_vars:
            _vars.update(self.user_vars)

        return template_payload(
            payload,
            _vars,
            silence_templating_errors,
            **(additional_vars or {}),
        )
