import re
import json

import boto3

from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.logging import get_task_logger


logger = get_task_logger('lambda_function.update-state', payload=tuple())

BATCH_LOG_GROUP = '/aws/batch/job'
LOG_CLIENT = boto3.client('logs')
DEFAULT_ERROR = 'UnknownError'
ERROR_REGEX = re.compile(r'^(?:cirrus\.?lib\.errors\.)?(?:([\.\w]+):)?\s*(.*)')


def lambda_handler(event, context):
    if 'error' not in event:
        return ProcessPayload.from_event(event)

    error = event.get('error', {})
    cause = json.loads(error['Cause'])
    logname = cause['Attempts'][-1]['Container']['LogStreamName']

    try:
        error_type, error_msg = get_error_from_batch(logname)
    except Exception:
        # lambda does not currently support exeception chaining,
        # so we have to log the original exception separately
        logger.exception("Original exception:")
        raise Exception("Unable to get error log")

    exception_class = type(error_type, (Exception,), {})
    raise exception_class(error_msg)


def get_error_from_batch(logname):
    logger.info('Getting error from %s/%s', BATCH_LOG_GROUP, logname)
    logs = LOG_CLIENT.get_log_events(
        logGroupName=BATCH_LOG_GROUP,
        logStreamName=logname,
    )
    msg = logs['events'][-1]['message']
    error_type, msg = ERROR_REGEX.match(msg).groups()
    return error_type or DEFAULT_ERROR, msg
