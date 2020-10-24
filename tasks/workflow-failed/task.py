import json
import logging
from os import getenv

import boto3
from boto3utils import s3
from cirruslib import Catalog, StateDB, get_task_logger

statedb = StateDB()
snsclient = boto3.client('sns')
logclient = boto3.client('logs')

FAILED_TOPIC_ARN = getenv('CIRRUS_FAILED_TOPIC_ARN', None)


def get_error_from_batch(logname):
    try:
        logs = logclient.get_log_events(logGroupName='/aws/batch/job', logStreamName=logname)
        msg = logs['events'][-1]['message'].lstrip('cirruslib.errors.')
        parts = msg.split(':', maxsplit=1)
        if len(parts) > 1:
            error_type = parts[0]
            msg = parts[1]
        return error_type, msg
    except Exception:
        return "Exception", "Failed getting logStream"


def handler(payload, context):
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger(f"{__name__}.convert-to-cog", catalog=catalog)

    # parse errors
    error = payload.get('error', {})

    # error type
    error_type = error.get('Error', "unknown")

    # check if cause is JSON
    try:
        cause = json.loads(error['Cause'])
        error_msg = 'unknown'
        if 'errorMessage' in cause:
            error_msg = cause.get('errorMessage', 'unknown')
        elif 'Attempts' in cause:
            try:
                # batch
                reason = cause['Attempts'][-1]['StatusReason']
                if 'Essential container in task exited' in reason:
                    # get the message from batch logs
                    logname = cause['Attempts'][-1]['Container']['LogStreamName']
                    error_type, error_msg = get_error_from_batch(logname)
            except Exception as err:
                logger.error(err, exc_info=True)
    except Exception:
        error_msg = error['Cause']

    error = f"{error_type}: {error_msg}"
    logger.info(error)

    try:
        if error_type == "InvalidInput":
            statedb.set_invalid(catalog['id'], error)
        else:
            statedb.set_failed(catalog['id'], error)
    except Exception as err:
        msg = f"Failed marking as failed: {err}"
        logger.error(msg, exc_info=True)
        raise err

    if FAILED_TOPIC_ARN is not None:
        try:
            item = statedb.dbitem_to_item(statedb.get_dbitem(catalog['id']))
            attrs = {
                'input_collections': {
                    'DataType': 'String',
                    'StringValue': item['input_collections']
                },
                'workflow': {
                    'DataType': 'String',
                    'StringValue': item['workflow']
                },
                'error': {
                    'DataType': 'String',
                    'StringValue': error
                }
            }
            logger.debug(f"Publishing item to {FAILED_TOPIC_ARN}")
            snsclient.publish(TopicArn=FAILED_TOPIC_ARN, Message=json.dumps(item), MessageAttributes=attrs)
        except Exception as err:
            msg = f"Failed publishing to {FAILED_TOPIC_ARN}: {err}"
            logger.error(msg, exc_info=True)
            raise err
    
    return catalog