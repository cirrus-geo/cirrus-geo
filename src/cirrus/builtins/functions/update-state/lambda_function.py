#!/usr/bin/env python
import json
import boto3

from os import getenv

from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.statedb import StateDB
from cirrus.lib.logging import get_task_logger


logger = get_task_logger('lambda_function.update-state', payload=tuple())

# envvars
PROCESS_SNS_TOPIC = getenv('CIRRUS_PROCESS_TOPIC_ARN', None)
FAILED_TOPIC_ARN = getenv('CIRRUS_FAILED_TOPIC_ARN', None)
INVALID_TOPIC_ARN = getenv('CIRRUS_INVALID_TOPIC_ARN', None)

# boto3 clients
SNS_CLIENT = boto3.client('sns')
SFN_CLIENT = boto3.client('stepfunctions')

# Cirrus state database
statedb = StateDB()

# how many execution events to request/check
# for an error cause in a FAILED state
MAX_EXECUTION_EVENTS = 10

FAILED = 'FAILED'


def unknown_error():
    return {
        'Error': 'Unknown',
        'Cause': 'update-state failed to find a specific error condition',
    }


def workflow_completed(input_payload, output_payload, error):
    # I think changing the state should be done before
    # trying the sns publish, but I could see it the other
    # way too. If we have issues here we might want to consider
    # a different order/behavior (fail on error or something?).
    statedb.set_completed(input_payload['id'])
    if not output_payload:
        return
    for next_payload in output_payload.next_payloads():
        next_payload.publish_to_sns(PROCESS_SNS_TOPIC)


def workflow_failed(input_payload, output_payload, error):
    # error type
    error_type = error.get('Error', "unknown")

    # check if cause is JSON
    try:
        cause = json.loads(error['Cause'])
        error_msg = 'unknown'
        if 'errorMessage' in cause:
            error_msg = cause.get('errorMessage', 'unknown')
    except Exception:
        error_msg = error['Cause']

    error = f"{error_type}: {error_msg}"
    logger.info(error)

    try:
        if error_type == "InvalidInput":
            statedb.set_invalid(input_payload['id'], error)
            notification_topic_arn = INVALID_TOPIC_ARN
        else:
            statedb.set_failed(input_payload['id'], error)
            notification_topic_arn = FAILED_TOPIC_ARN
    except Exception as err:
        msg = f"Failed marking as failed: {err}"
        logger.error(msg, exc_info=True)
        raise err

    if notification_topic_arn is not None:
        try:
            item = statedb.dbitem_to_item(statedb.get_dbitem(input_payload['id']))
            attrs = {
                'collections': {
                    'DataType': 'String',
                    'StringValue': item['collections']
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
            logger.debug(f"Publishing item to {notification_topic_arn}")
            SNS_CLIENT.publish(
                TopicArn=notification_topic_arn,
                Message=json.dumps(item),
                MessageAttributes=attrs,
            )
        except Exception as err:
            msg = f"Failed publishing to {notification_topic_arn}: {err}"
            logger.error(msg, exc_info=True)
            raise err


def get_execution_error(arn):
    error = None

    try:
        history = SFN_CLIENT.get_execution_history(
            executionArn=arn,
            maxResults=MAX_EXECUTION_EVENTS,
            reverseOrder=True,
        )
        for event in history['events']:
            try:
                if 'stateEnteredEventDetails' in event:
                    details = event['stateEnteredEventDetails']
                    error = json.loads(details['input'])['error']
                    break
                elif 'lambdaFunctionFailedEventDetails' in event:
                    error = event['lambdaFunctionFailedEventDetails']
                    # for some dumb reason these errors have lowercase key names
                    error = {key.capitalize(): val for key, val in error.items()}
                    break
            except KeyError:
                pass
        else:
            logger.warning(
                'Could not find execution error in last %s events',
                MAX_EXECUTION_EVENTS,
            )
    except Exception as e:
        logger.exception(e)

    if error:
        logger.debug("Error found: '%s'", error)
    else:
        error = unknown_error()
    return error



# TODO: in cirrus.lib make a factory class that returns classes
# for each error type, and generalize the processing here into
# a well-known type interface
def parse_event(event):
    # return a tuple of:
    #   - ProcessPayload object
    #   - status string
    #   - error object
    try:
        if 'error' in event:
            logger.debug('looks like a payload with an error message, i.e., workflow-failed')
            return (
                ProcessPayload.from_event(event),
                None,
                FAILED,
                event.get('error', {}),
            )
        elif event.get('source', '') == "aws.states":
            status = event['detail']['status']
            logger.debug("looks like a step function event message, status '%s'", status)
            error = None
            if status == FAILED:
                error = get_execution_error(event['detail']['executionArn'])
            return (
                ProcessPayload(json.loads(event['detail']['input'])),
                ProcessPayload(json.loads(event['detail']['output']))
                    if event['detail'].get('output', None) else None,
                status,
                error,
            )
        else:
            raise Exception()
    except Exception:
        logger.error('Unknown event: %s', json.dumps(event))
        return None, None, None, None


def lambda_handler(event, context={}):
    logger.debug(event)
    input_payload, output_payload, status, error = parse_event(event)

    status_update_map = {
        FAILED: workflow_failed,
        'SUCCEEDED': workflow_completed,
    }

    if status not in status_update_map:
        logger.info("Status does not support updates")
        return

    status_update_map[status](input_payload, output_payload, error)
