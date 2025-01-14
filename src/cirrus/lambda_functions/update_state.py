#!/usr/bin/env python
import json

from dataclasses import dataclass
from os import getenv
from typing import Any

from cirrus.lib.enums import SfnStatus
from cirrus.lib.events import WorkflowEventManager
from cirrus.lib.logging import get_task_logger
from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.utils import SNSPublisher, SQSPublisher, cold_start, get_client

cold_start()

logger = get_task_logger("function.update-state", payload=())

# boto3 clients
SFN_CLIENT = get_client("stepfunctions")

# how many execution events to request/check
# for an error cause in a FAILED state
MAX_EXECUTION_EVENTS = 10

INVALID_EXCEPTIONS = (
    "cirrus.lib.errors.InvalidInput",
    "stactask.exceptions.InvalidInput",
)


@dataclass
class Execution:
    arn: str
    input: ProcessPayload
    url: str
    output: ProcessPayload | None
    status: SfnStatus
    error: dict | None

    def update_state(self, wfem) -> None:
        status_update_map = {
            SfnStatus.SUCCEEDED: workflow_completed,
            SfnStatus.FAILED: workflow_failed,
            SfnStatus.ABORTED: workflow_aborted,
            SfnStatus.TIMED_OUT: workflow_failed,
        }

        if self.status not in status_update_map:
            raise ValueError(f"Status does not support updates: {self.status}")

        status_update_map[self.status](self, wf_event_manager=wfem)

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "Execution":
        try:
            arn = event["detail"]["executionArn"]

            _input = ProcessPayload.from_event(json.loads(event["detail"]["input"]))

            eout = event["detail"].get("output", None)
            output = ProcessPayload.from_event(json.loads(eout)) if eout else None

            status = event["detail"]["status"]
            error = None

            if status == SfnStatus.SUCCEEDED:
                pass
            elif status == SfnStatus.FAILED:
                error = get_execution_error(arn)
            elif status == SfnStatus.ABORTED:
                pass
            elif status == SfnStatus.TIMED_OUT:
                error = mk_error(
                    "TimedOutError",
                    "The step function execution timed out.",
                )
            else:
                logger.warning("Unknown status: %s", status)

            return cls(
                arn=arn,
                input=_input,
                url=(
                    event["url"]
                    if "url" in event
                    else ProcessPayload.upload_to_s3(_input)
                ),
                output=output,
                status=status,
                error=error,
            )
        except Exception as e:
            raise Exception(f"Unknown event: {json.dumps(event)}") from e


def mk_error(error: str, cause: str) -> dict[str, str]:
    return {
        "Error": error,
        "Cause": cause,
    }


def workflow_completed(
    execution: Execution,
    wf_event_manager: WorkflowEventManager,
) -> None:
    # I think changing the state should be done before
    # trying the sns publish, but I could see it the other
    # way too. If we have issues here we might want to consider
    # a different order/behavior (fail on error or something?).
    wf_event_manager.succeeded(execution.input["id"], execution_arn=execution.arn)

    publish_topic_arn = getenv("CIRRUS_PUBLISH_TOPIC_ARN")
    if execution.output and publish_topic_arn:
        with SNSPublisher(publish_topic_arn, logger=logger) as publisher:
            if messages := execution.output.items_to_sns_messages():
                publisher.send(messages)

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
    wf_event_manager.aborted(execution.input["id"], execution_arn=execution.arn)


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
                execution.input["id"],
                error,
                execution_arn=execution.arn,
            )
        elif error_type == "TimedOutError":
            wf_event_manager.timed_out(
                execution.input["id"],
                error,
                execution_arn=execution.arn,
            )
        else:
            wf_event_manager.failed(
                execution.input["id"],
                error,
                execution_arn=execution.arn,
            )
    except Exception:
        logger.exception("Unable to update state")
        raise


def get_execution_error(arn: str) -> dict[str, str]:
    error = None

    try:
        history = SFN_CLIENT.get_execution_history(
            executionArn=arn,
            maxResults=MAX_EXECUTION_EVENTS,
            reverseOrder=True,
        )
        for event in history["events"]:
            try:
                if "stateEnteredEventDetails" in event:
                    details = event["stateEnteredEventDetails"]
                    error = json.loads(details["input"])["error"]
                    break

                if "lambdaFunctionFailedEventDetails" in event:
                    error = event["lambdaFunctionFailedEventDetails"]
                    # for some dumb reason these errors have lowercase key names
                    error = {key.capitalize(): val for key, val in error.items()}
                    break
            except KeyError:
                pass
        else:
            logger.warning(
                "Could not find execution error in last %s events",
                MAX_EXECUTION_EVENTS,
            )
    except Exception:
        logger.exception("Failed to get stepfunction execution history")

    if error:
        logger.debug("Error found: '%s'", error)
    else:
        error = mk_error(
            "Unknown",
            "update-state failed to find a specific error condition.",
        )
    return error


@WorkflowEventManager.with_wfem(logger=logger)
def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    wfem: WorkflowEventManager,
) -> None:
    logger.debug(event)
    Execution.from_event(event).update_state(wfem)
