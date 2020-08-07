import boto3
import json
import logging

from cirruslib import Catalogs, StateDB
from os import getenv
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'INFO'))

stepfunctions = boto3.client('stepfunctions')

statedb = StateDB()


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    catids = []
    for catalog in Catalogs.from_payload(payload):
        logger.debug(f"Catalog: {json.dumps(catalog)}")
        try:
            # get workflow ARN
            arn = getenv('BASE_WORKFLOW_ARN') + catalog['process']['workflow']

            # invoke step function
            logger.info(f"Running {arn} on {catalog['id']}")
            exe_response = stepfunctions.start_execution(stateMachineArn=arn, input=json.dumps(catalog.get_payload()))
            logger.debug(f"Start execution response: {exe_response}")

            # set state to PROCESSING
            # TODO - what happens if step function startws but set_processing failed - it will be stuck in queue state
            resp = statedb.set_processing(catalog['id'], exe_response['executionArn'])
            logger.debug(f"Set process response: {resp}")
            catids.append(catalog['id'])
        except Exception as err:
            msg = f"start-workflow: failed starting {catalog['id']} ({err})"
            logger.error(msg)
            logger.error(format_exc())
            statedb.set_failed(catalog['id'], msg)

    return catids
