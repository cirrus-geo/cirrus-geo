import boto3
import json
import logging

from boto3utils import s3
from cirruslib.statedb import StateDB
from os import getenv, path as op
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

statedb = StateDB()
snsclient = boto3.client('sns')
logclient = boto3.client('logs')

CATALOG_BUCKET = getenv('CIRRUS_CATALOG_BUCKET', None)
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


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    # set the event ID if payload is on s3
    prefix = f"s3://{CATALOG_BUCKET}/batch/"
    if 'url' in payload:
        # this happens when error happens during batch processing 
        payload['id'] = op.dirname(payload['url'])[len(prefix):]
    elif 'Parameters' in payload and 'url' in payload['Parameters']:
        # this happens when error happens during post-batch processing
        payload['id'] = op.dirname(payload['Parameters']['url'])[len(prefix):]

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
                logger.error(err)
                logger.error(format_exc())
    except Exception:
        error_msg = error['Cause']

    error = f"{error_type}: {error_msg}"
    logger.info(error)

    try:
        if error_type == "InvalidInput":
            statedb.set_invalid(payload['id'], error)
        else:
            statedb.set_failed(payload['id'], error)
    except Exception as err:
        msg = f"Failed marking as failed: {err}"
        logger.error(msg)
        logger.error(format_exc())
        raise err

    if FAILED_TOPIC_ARN is not None:
        try:
            item = statedb.dbitem_to_item(statedb.get_dbitem(payload['id']))
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
            logger.debug(f"Publishing item {item['catid']} to {FAILED_TOPIC_ARN}")
            snsclient.publish(TopicArn=FAILED_TOPIC_ARN, Message=json.dumps(item), MessageAttributes=attrs)
        except Exception as err:
            msg = f"Failed publishing {payload['id']} to {FAILED_TOPIC_ARN}: {err}"
            logger.error(msg)
            logger.error(format_exc())
            raise err
    
    return payload