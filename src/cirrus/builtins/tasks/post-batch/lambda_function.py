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

    cause = json.loads(error.get("Cause", {}))
    attempts = cause.get("Attempts", [])
    if not attempts:
        logger.exception(f"Original error: {json.dumps(error)}")
        raise Exception("Unable to get error log: Attempts is empty")

    logname = attempts[-1].get("Container", {}).get("LogStreamName")
    if not logname:
        logger.exception(f"Original error: {json.dumps(error)}")
        raise Exception(
            "Unable to get error log: Container or LogStreamName for last Attempt is missing"
        )

    try:
        error_type, error_msg = get_error_from_batch(logname)
    except Exception as e:
        # lambda does not currently support exeception chaining,
        # so we have to log the original exception separately
        logger.exception(f"Original error: {json.dumps(error)}")
        raise Exception(f"Unable to get error log '{BATCH_LOG_GROUP}/{logname}': {e}")

    exception_class = type(error_type, (Exception,), {})
    raise exception_class(error_msg)


def get_error_from_batch(logname: str) -> Optional[Tuple[str, str]]:
    logger.info("Getting error from %s/%s", BATCH_LOG_GROUP, logname)
    logs = LOG_CLIENT.get_log_events(
        logGroupName=BATCH_LOG_GROUP,
        logStreamName=logname,
    )
    msg = logs["events"][-1]["message"]
    error_type, msg = ERROR_REGEX.match(msg).groups()
    return error_type or DEFAULT_ERROR, msg
