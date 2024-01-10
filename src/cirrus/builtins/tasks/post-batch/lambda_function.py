import json
import re
from typing import Any, Optional, Tuple

import boto3

from cirrus.lib2.logging import get_task_logger
from cirrus.lib2.process_payload import ProcessPayload

logger = get_task_logger("task.post-batch", payload=tuple())

BATCH_LOG_GROUP = "/aws/batch/job"
LOG_CLIENT = boto3.client("logs")
DEFAULT_ERROR = "UnknownError"
ERROR_REGEX = re.compile(r"^(?:cirrus\.?lib\.errors\.)?(?:([\.\w]+):)?\s*(.*)")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if "error" not in event:
        return ProcessPayload.from_event(event).get_payload()

    error = event.get("error", {})
    if "Cause" not in error:
        logger.exception(f"Original error: {json.dumps(error)}")
        raise Exception("Unable to get error log: Cause is not defined")

    cause = json.loads(error.get("Cause", "{}"))
    attempts = cause.get("Attempts", [])
    if not attempts:
        logger.exception(f"Original error: {json.dumps(error)}")
        raise Exception("Unable to get error log: Attempts is empty")

    attempt = attempts[-1]
    container = attempt.get("Container")
    if container is None:
        logger.exception(f"Original error: {json.dumps(error)}")
        raise Exception(
            "Unable to get error log: Container for last Attempt is missing"
        )

    logname = container.get("LogStreamName")
    if not logname:
        logger.exception(f"Original error: {json.dumps(error)}")
        raise Exception(
            "Unable to get error log: LogStreamName for last Attempt is missing"
        )

    error_from_batch = None
    try:
        error_from_batch = get_error_from_batch(logname)
    except Exception as e:
        # lambda does not currently support exeception chaining,
        # so we have to log the original exception separately
        logger.exception(
            f"Unable to get error log '{BATCH_LOG_GROUP}/{logname}' because {e}, original error: {json.dumps(error)}"
        )

    if error_from_batch:
        error_type, error_msg = error_from_batch
        exception_class = type(error_type, (Exception,), {})
        raise exception_class(error_msg)
    else:
        # if the cloudwatch error log cannot be retrieved, it's likely that the container
        # didn't start and nothing was logged anyway, so we log the reason for that instead
        container_reason = container.get(
            "Reason"
        )  # e.g., "DockerTimeoutError: Could not transition to created; timed out after waiting 4m0s"
        status_reason = attempt.get("StatusReason")  # e.g., "Task failed to start"
        raise Exception(
            "Unable to get error log, container likely never ran. "
            f"Container Reason: {container_reason}; Status Reason: {status_reason}"
        )


def get_error_from_batch(logname: str) -> Optional[Tuple[str, str]]:
    logger.info("Getting error from %s/%s", BATCH_LOG_GROUP, logname)
    logs = LOG_CLIENT.get_log_events(
        logGroupName=BATCH_LOG_GROUP,
        logStreamName=logname,
    )
    msg = logs["events"][-1]["message"]
    error_type, msg = ERROR_REGEX.match(msg).groups()
    return error_type or DEFAULT_ERROR, msg
