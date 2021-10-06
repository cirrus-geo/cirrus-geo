import boto3
import json
from cirruslib import Catalog


LOG_CLIENT = boto3.client('logs')


class BaseException(Exception):
    pass


def lambda_handler(payload, context):
    if 'error' in payload:
        error = payload.get('error', {})
        cause = json.loads(error['Cause'])
        logname = cause['Attempts'][-1]['Container']['LogStreamName']
        error_type, error_msg = get_error_from_batch(logname)
        exception_class = type(error_type, (BaseException, Exception), {})
        raise exception_class(error_msg)
    catalog = Catalog.from_payload(payload)
    return catalog


def get_error_from_batch(logname):
    try:
        logs = LOG_CLIENT.get_log_events(logGroupName='/aws/batch/job', logStreamName=logname)
        msg = logs['events'][-1]['message'].lstrip('cirruslib.errors.')
        parts = msg.split(':', maxsplit=1)
        if len(parts) > 1:
            error_type = parts[0]
            msg = parts[1]
            return error_type, msg
        return "Unknown", msg
    except Exception:
        return "Exception", "Unable to get Error Log"
