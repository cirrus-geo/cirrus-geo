import re
import json

import boto3

from cirruslib import Catalog


LOG_CLIENT = boto3.client('logs')
DEFAULT_ERROR = 'UnknownError'


def lambda_handler(payload, context):
    if 'error' not in payload:
        catalog = Catalog.from_payload(payload)
        return catalog

    error = payload.get('error', {})
    cause = json.loads(error['Cause'])
    logname = cause['Attempts'][-1]['Container']['LogStreamName']

    try:
        error_type, error_msg = get_error_from_batch(logname)
    except Exception as e:
        raise Exception("Unable to get error log") from e

    exception_class = type(error_type, (Exception,), {})
    raise exception_class(error_msg)


def get_error_from_batch(logname):
    logs = LOG_CLIENT.get_log_events(
        logGroupName='/aws/batch/job',
        logStreamName=logname,
    )
    msg = logs['events'][-1]['message'].removeprefix('cirruslib.errors.')

    error_regex = re.compile(r'(^[\.\w]+:)?\s*(.*)')
    error_type, msg = error_regex.match(msg).groups()

    return error_type or DEFAULT_ERROR, msg
