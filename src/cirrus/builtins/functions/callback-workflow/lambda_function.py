#!/usr/bin/env python
import boto3

from cirrus.lib.logging import get_task_logger
from cirrus.lib.statedb import SUCCESS_STATES, FAILED_STATES


LAMBDA_TYPE = 'lambda_function'

logger = get_task_logger(f'{LAMBDA_TYPE}.workflow-callback', payload=tuple())

SFN = boto3.client('stepfunctions')


def lambda_handler(event, context={}):
    logger.debug(event)
    for record in event['Records']:
        callback_token = record['dynamodb']['Keys']['callback_token']['S']

        if record['eventName'] == 'REMOVE':
            logger.debug(f"Skipping removed callback: token '{callback_token}'")
            continue

        item_id = record['dynamodb']['NewImage']['workflow_collections256_itemids256']['S']
        state = record['dynamodb']['NewImage']['workflow_state']['S']
        logger.info(f"Processing item '{item_id}'")

        # Note that the expiration is set when a final state is set on a record.
        # If we need a flag in the DB to indicate that the callback has actually
        # been triggered successfully, then we could not set the expiration on that
        # state update, instead doing in this function after a successful send_task_*.
        try:
            if state in SUCCESS_STATES:
                logger.info(
                    f"Calling back token '{callback_token}' for state '{state}' as success",
                )
                SFN.send_task_success(
                    taskToken=callback_token,
                    output='',  # I"m not sure how to use this, but it is required so...
                )

            elif state in FAILED_STATES:
                logger.info(
                    f"Calling back token '{callback_token}' for state '{state}' as failure",
                )
                SFN.send_task_failure(taskToken=callback_token)

            else:
                logger.info(f"Skipping item not in final state: id '{item_id}', state '{state}'")
        except SFN.exceptions.InvalidToken:
            logger.error(
                "No step function tasks are awaiting callback '%s'",
                callback_token,
            )

    return f"Successfully processed {len(event['Records'])} records."
