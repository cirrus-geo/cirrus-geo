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

bucket = getenv('CIRRUS_CATALOG_BUCKET', None)


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    # set the event ID if payload is on s3
    prefix = f"s3://{bucket}/batch/"
    if 'url' in payload:
        # this happens when error happens during batch processing 
        payload['id'] = op.dirname(payload['url'])[len(prefix):]
    elif 'Parameters' in payload and 'url' in payload['Parameters']:
        # this happens when error happens during post-batch processing
        payload['id'] = op.dirname(payload['Parameters']['url'])[len(prefix):]

    try:
        #tb = '-'
        error = payload.get('error', None)
        error_type = "Exception"
        msg = 'Unknown error'
        if error is not None:
            if 'Error' in error:
                error_type = error['Error']
            try:
                cause = json.loads(error['Cause'])
                if 'errorMessage' in cause:
                    msg = cause.get('errorMessage', '')
                    #tb = cause.get('stackTrace', '-')
                elif 'Attempts' in cause:
                    msg = f"batch processing failed - {cause['Attempts'][-1]['StatusReason']}"
            except:
                msg = error.get('Cause', error)

        logger.info(f"Workflow Failed ({payload['id']}): {msg}")

        if error_type == "InvalidInput":
            statedb.set_invalid(payload['id'], msg)
            logger.debug(f"Set {payload['id']} as invalid")
        else:
            statedb.set_failed(payload['id'], msg)
            logger.debug(f"Set {payload['id']} as failed")
    
        return payload
    except Exception as err:
        msg = f"Failed marking {payload['id']} as failed: {err}"
        logger.error(msg)
        logger.error(format_exc())
        raise err

    