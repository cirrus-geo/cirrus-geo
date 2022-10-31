#!/usr/bin/env python
import json
from os import getenv

import boto3

from cirrus.lib2.logging import get_task_logger
from cirrus.lib2.process_payload import ProcessPayload
from cirrus.lib2.statedb import StateDB
from cirrus.lib2.utils import batch_handler

logger = get_task_logger("lambda_function.update-state", payload=tuple())

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


def mk_error(error, cause):
    return {
        "Error": error,
        "Cause": cause,
    }


def send_batch(messages):
    entries = [{"Id": str(idx), "MessageBody": msg} for idx, msg in enumerate(messages)]
    resp = QUEUE.send_messages(Entries=entries)
    logger.debug(f"Published {len(messages)} payloads to {PROCESS_QUEUE_URL}")
    return resp


def workflow_completed(input_payload, output_payload, error):
    # I think changing the state should be done before
    # trying the sns publish, but I could see it the other
    # way too. If we have issues here we might want to consider
    # a different order/behavior (fail on error or something?).
    statedb.set_completed(input_payload["id"])
    if not output_payload:
        return
    with batch_handler(send_batch, {}, "messages", batch_size=10) as handler:
        for next_payload in output_payload.next_payloads():
            handler.add(json.dumps(next_payload))


def workflow_aborted(input_payload, output_payload, error):
    statedb.set_aborted(input_payload["id"])


def workflow_failed(input_payload, output_payload, error):
    # error type
    error_type = error.get("Error", "unknown")

    # check if cause is JSON
    try:
        cause = json.loads(error["Cause"])
        error_msg = "unknown"
        if "errorMessage" in cause:
            error_msg = cause.get("errorMessage", "unknown")
    except Exception:
        error_msg = error["Cause"]

    error = f"{error_type}: {error_msg}"
    logger.info(error)

    try:
        if error_type in INVALID_EXCEPTIONS:
            statedb.set_invalid(input_payload["id"], error)
            notification_topic_arn = INVALID_TOPIC_ARN
        else:
            statedb.set_failed(input_payload["id"], error)
            notification_topic_arn = FAILED_TOPIC_ARN
    except Exception:
        logger.exception("Unable to update state")
        raise

    if notification_topic_arn is not None:
        try:
            item = statedb.dbitem_to_item(statedb.get_dbitem(input_payload["id"]))
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


def get_execution_error(arn):
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


# TODO: in cirrus.lib make a factory class that returns classes
# for each error type, and generalize the processing here into
# a well-known type interface
def parse_event(event):
    # return a tuple of:
    #   - workflow input ProcessPayload object
    #   - workflow output ProcessPayload object or None (if not success)
    #   - status string
    #   - error object
    if "error" in event:
        logger.debug(
            "looks like a payload with an error message, i.e., workflow-failed"
        )
        return (
            ProcessPayload.from_event(event),
            None,
            FAILED,
            event.get("error", {}),
        )
    elif event.get("source", "") == "aws.states":
        status = event["detail"]["status"]
        error = None
        if status == SUCCEEDED:
            pass
        elif status == FAILED:
            error = get_execution_error(event["detail"]["executionArn"])
        elif status == ABORTED:
            pass
        elif status == TIMED_OUT:
            error = mk_error(
                "TimedOutError",
                "The step function execution timed out.",
            )
        else:
            logger.warning("Unknown status: %s", status)
        return (
            ProcessPayload.from_event(json.loads(event["detail"]["input"])),
            ProcessPayload.from_event(json.loads(event["detail"]["output"]))
            if event["detail"].get("output", None)
            else None,
            status,
            error,
        )
    else:
        raise Exception(f"Unknown event: {json.dumps(event)}")


def lambda_handler(event, context={}):
    logger.debug(event)
    input_payload, output_payload, status, error = parse_event(event)

    status_update_map = {
        SUCCEEDED: workflow_completed,
        FAILED: workflow_failed,
        ABORTED: workflow_aborted,
        TIMED_OUT: workflow_failed,
    }

    if status not in status_update_map:
        logger.info("Status does not support updates: %s", status)
        return

    status_update_map[status](input_payload, output_payload, error)
