#!/usr/bin/env python
import json
from dataclasses import dataclass
from os import getenv
from typing import Any, Dict, List, Optional

import boto3

from cirrus.lib2.logging import get_task_logger
from cirrus.lib2.process_payload import ProcessPayload
from cirrus.lib2.statedb import StateDB
from cirrus.lib2.utils import batch_handler

logger = get_task_logger("function.update-state", payload=tuple())

# envvars
FAILED_TOPIC_ARN = getenv("CIRRUS_FAILED_TOPIC_ARN", None)
INVALID_TOPIC_ARN = getenv("CIRRUS_INVALID_TOPIC_ARN", None)
PROCESS_QUEUE_URL = getenv("CIRRUS_PROCESS_QUEUE_URL")

# boto3 clients
SNS_CLIENT = boto3.client("sns")
SFN_CLIENT = boto3.client("stepfunctions")
SQS_CLIENT = boto3.resource("sqs")
QUEUE = SQS_CLIENT.Queue(PROCESS_QUEUE_URL)

# Cirrus state database
statedb = StateDB()

# how many execution events to request/check
# for an error cause in a FAILED state
MAX_EXECUTION_EVENTS = 10

SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
ABORTED = "ABORTED"
TIMED_OUT = "TIMED_OUT"

INVALID_EXCEPTIONS = (
    "InvalidInput",
    "stactask.exceptions.InvalidInput",
)


@dataclass
class Execution:
    arn: str
    input: ProcessPayload
    output: ProcessPayload
    status: str
    error: Optional[dict]

    def update_state(self) -> None:
        status_update_map = {
            SUCCEEDED: workflow_completed,
            FAILED: workflow_failed,
            ABORTED: workflow_aborted,
            TIMED_OUT: workflow_failed,
        }

        if self.status not in status_update_map:
            raise ValueError(f"Status does not support updates: {self.status}")

        status_update_map[self.status](self)

    @classmethod
    def from_event(cls, event: Dict[str, Any]) -> "Execution":
        try:
            arn = event["detail"]["executionArn"]

            _input = ProcessPayload.from_event(json.loads(event["detail"]["input"]))

            eout = event["detail"].get("output", None)
            output = ProcessPayload.from_event(json.loads(eout)) if eout else None

            status = event["detail"]["status"]
            error = None

            if status == SUCCEEDED:
                pass
            elif status == FAILED:
                error = get_execution_error(arn)
            elif status == ABORTED:
                pass
            elif status == TIMED_OUT:
                error = mk_error(
                    "TimedOutError",
                    "The step function execution timed out.",
                )
            else:
                logger.warning("Unknown status: %s", status)

            return cls(
                arn=arn,
                input=_input,
                output=output,
                status=status,
                error=error,
            )
        except Exception:
            raise Exception(f"Unknown event: {json.dumps(event)}")


def mk_error(error: str, cause: str) -> Dict[str, str]:
    return {
        "Error": error,
        "Cause": cause,
    }


def send_batch(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    entries = [{"Id": str(idx), "MessageBody": msg} for idx, msg in enumerate(messages)]
    resp = QUEUE.send_messages(Entries=entries)
    logger.debug(f"Published {len(messages)} payloads to {PROCESS_QUEUE_URL}")
    return resp


def workflow_completed(execution: Execution) -> None:
    # I think changing the state should be done before
    # trying the sns publish, but I could see it the other
    # way too. If we have issues here we might want to consider
    # a different order/behavior (fail on error or something?).
    statedb.set_completed(execution.input["id"], execution_arn=execution.arn)
    if execution.output:
        with batch_handler(send_batch, {}, "messages", batch_size=10) as handler:
            for next_payload in execution.output.next_payloads():
                handler.add(json.dumps(next_payload))


def workflow_aborted(execution: Execution) -> None:
    statedb.set_aborted(execution.input["id"], execution_arn=execution.arn)


def workflow_failed(execution: Execution) -> None:
    error_type = "unknown"
    error_msg = "unknown"

    if execution.error:
        error_type = execution.error.get("Error", "unknown")
        # check if cause is JSON
        try:
            cause = json.loads(execution.error["Cause"])
            if "errorMessage" in cause:
                error_msg = cause.get("errorMessage", "unknown")
        except Exception:
            error_msg = execution.error["Cause"]

    error = f"{error_type}: {error_msg}"
    logger.info(error)

    try:
        if error_type in INVALID_EXCEPTIONS:
            statedb.set_invalid(
                execution.input["id"], error, execution_arn=execution.arn
            )
            notification_topic_arn = INVALID_TOPIC_ARN
        else:
            statedb.set_failed(
                execution.input["id"], error, execution_arn=execution.arn
            )
            notification_topic_arn = FAILED_TOPIC_ARN
    except Exception:
        logger.exception("Unable to update state")
        raise

    if notification_topic_arn is not None:
        try:
            item = statedb.dbitem_to_item(statedb.get_dbitem(execution.input["id"]))
            attrs = {
                "collections": {
                    "DataType": "String",
                    "StringValue": item["collections"],
                },
                "workflow": {"DataType": "String", "StringValue": item["workflow"]},
                "error": {"DataType": "String", "StringValue": error},
            }
            logger.debug(f"Publishing item to {notification_topic_arn}")
            SNS_CLIENT.publish(
                TopicArn=notification_topic_arn,
                Message=json.dumps(item),
                MessageAttributes=attrs,
            )
        except Exception:
            logger.exception(f"Failed publishing to {notification_topic_arn}")
            raise


def get_execution_error(arn: str) -> Dict[str, str]:
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
                elif "lambdaFunctionFailedEventDetails" in event:
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


def lambda_handler(event: Dict[str, Any], _context: Any) -> None:
    logger.debug(event)
    Execution.from_event(event).update_state()
