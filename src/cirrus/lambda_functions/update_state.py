#!/usr/bin/env python
from __future__ import annotations

import json

from dataclasses import dataclass
from os import getenv
from typing import Any, Self

from cirrus.lib.cirrus_payload import CirrusPayload
from cirrus.lib.enums import SfnStatus
from cirrus.lib.events import WorkflowEventManager
from cirrus.lib.logging import CirrusLoggerAdapter
from cirrus.lib.payload_bucket import PayloadBucket
from cirrus.lib.payload_manager import PayloadManager
from cirrus.lib.utils import SNSPublisher, SQSPublisher, cold_start

cold_start()

INVALID_EXCEPTIONS = (
    "cirrus.lib.errors.InvalidInput",
    "stactask.exceptions.InvalidInput",
)

logger = CirrusLoggerAdapter("function.update-state")

payload_bucket = PayloadBucket()


def workflow_succeeded(
    execution: Execution,
    wf_event_manager: WorkflowEventManager,
) -> None:
    output_url: str | None = None
    if not execution.output:
        logger.warning("Succeeded execution does not have an output payload")
    else:
        output_url = payload_bucket.upload_output_payload(
            execution.output.payload,
            execution.input.payload["id"],
            execution.id,
        )

    # I think changing the state should be done before
    # trying the sns publish, but I could see it the other
    # way too. If we have issues here we might want to consider
    # a different order/behavior (fail on error or something?).
    wf_event_manager.succeeded(
        execution.input.payload["id"],
        execution_arn=execution.arn,
        input_payload_url=execution.input_payload_url,
        output_payload_url=output_url,
    )

    publish_topic_arn = getenv("CIRRUS_PUBLISH_TOPIC_ARN")
    if execution.output and publish_topic_arn:
        with SNSPublisher(publish_topic_arn, logger=logger) as publisher:
            for message in execution.output.items_to_sns_messages():
                publisher.add(message)

    process_queue_url = getenv("CIRRUS_PROCESS_QUEUE_URL")
    if execution.output and process_queue_url:
        # TODO: add test of workflow chaining
        with SQSPublisher(process_queue_url, logger=logger) as publisher:
            for next_payload in execution.output.next_payloads():
                publisher.add(json.dumps(next_payload))


def workflow_aborted(
    execution: Execution,
    wf_event_manager: WorkflowEventManager,
) -> None:
    wf_event_manager.aborted(
        execution.input.payload["id"],
        execution_arn=execution.arn,
        input_payload_url=execution.input_payload_url,
    )


def workflow_failed(
    execution: Execution,
    wf_event_manager: WorkflowEventManager,
) -> None:
    error_type = "unknown"
    error_msg = "unknown"

    if execution.error:
        error_type = execution.error.get("Error", "unknown")
        # check if cause is JSON
        try:
            cause = json.loads(execution.error["Cause"])
            if "errorMessage" in cause:
                error_msg = cause.get("errorMessage", "unknown")
        except Exception:  # noqa: BLE001
            error_msg = execution.error["Cause"]

    error = f"{error_type}: {error_msg}"
    logger.info(error)

    try:
        if error_type in INVALID_EXCEPTIONS:
            wf_event_manager.invalid(
                execution.input.payload["id"],
                error,
                execution_arn=execution.arn,
                input_payload_url=execution.input_payload_url,
            )
        elif error_type == "TimedOutError":
            wf_event_manager.timed_out(
                execution.input.payload["id"],
                error,
                execution_arn=execution.arn,
                input_payload_url=execution.input_payload_url,
            )
        else:
            wf_event_manager.failed(
                execution.input.payload["id"],
                error,
                execution_arn=execution.arn,
                input_payload_url=execution.input_payload_url,
            )
    except Exception:
        logger.exception("Unable to update state")
        raise


def get_execution_error(event: dict) -> dict[str, str]:
    error = event["detail"].get("error") or "Unknown"
    cause = event["detail"].get("cause") or (
        "No error cause was found in the event. Check that the 'Fail' state in the "
        "workflow step function definition includes 'ErrorPath' and 'CausePath' fields "
        "that capture the error name and error cause."
    )
    return {"Error": error, "Cause": cause}


STATUS_UPDATE_MAP = {
    SfnStatus.SUCCEEDED: workflow_succeeded,
    SfnStatus.FAILED: workflow_failed,
    SfnStatus.ABORTED: workflow_aborted,
    SfnStatus.TIMED_OUT: workflow_failed,
}


@dataclass
class Execution:
    arn: str
    id: str
    input: PayloadManager
    output: PayloadManager | None
    status: SfnStatus
    error: dict | None

    @property
    def input_payload_url(self) -> str:
        return payload_bucket.get_input_payload_url(
            self.input.payload["id"],
            self.id,
        )

    def update_state(self, wfem) -> None:
        update_fn = STATUS_UPDATE_MAP.get(self.status)

        if not update_fn:
            raise ValueError(f"Status does not support updates: {self.status}")

        return update_fn(self, wf_event_manager=wfem)

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> Self:
        try:
            arn = event["detail"]["executionArn"]
            id = event["detail"]["name"]
            status = event["detail"]["status"]

            # Check if input/output details are included before accessing.
            # If the combined escaped input and escaped output sent to
            # EventBridge exceeds 248 KiB, then the input will be excluded,
            # and if the output is longer than that limit it will also be excluded.
            # See: https://docs.aws.amazon.com/step-functions/latest/dg/eventbridge-integration.html#event-detail-execution-status-change-remarks
            input_details: dict[str, Any] = (
                event["detail"].get("inputDetails", {}) or {}
            )
            if not input_details.get("included", False):
                # TODO: optionally fallback to SFN API
                error_msg = "Input details not included in EventBridge event"
                logger.error(error_msg)
                raise ValueError(error_msg)

            output_details: dict[str, Any] = (
                event["detail"].get("outputDetails", {}) or {}
            )
            if status == SfnStatus.SUCCEEDED and not output_details.get(
                "included",
                False,
            ):
                # TODO: optionally fallback to SFN API
                error_msg = "Output details not included in EventBridge event"
                logger.error(error_msg)
                raise ValueError(error_msg)

            _input = PayloadManager(
                CirrusPayload.from_event(
                    json.loads(event["detail"]["input"]),
                ),
            )

            eout = event["detail"].get("output", None)
            output = (
                PayloadManager(CirrusPayload.from_event(json.loads(eout)))
                if eout
                else None
            )

            error = None

            if status == SfnStatus.SUCCEEDED:
                pass
            elif status == SfnStatus.FAILED:
                error = get_execution_error(event)
            elif status == SfnStatus.ABORTED:
                pass
            elif status == SfnStatus.TIMED_OUT:
                error = {
                    "Error": "TimedOutError",
                    "Cause": "The step function execution timed out.",
                }
            else:
                logger.warning("Unknown status: %s", status)

            return cls(
                arn=arn,
                id=id,
                input=_input,
                output=output,
                status=status,
                error=error,
            )
        except Exception as e:
            error_msg = f"Failed to parse event: {e} | Event: {json.dumps(event)}"
            raise Exception(error_msg) from e


@WorkflowEventManager.with_wfem(logger=logger)
def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    wfem: WorkflowEventManager,
) -> None:
    logger.debug(event)
    Execution.from_event(event).update_state(wfem)
