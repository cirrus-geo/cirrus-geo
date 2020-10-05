import boto3
import json
import logging
import uuid

from boto3utils import s3
from cirruslib.statedb import StateDB
from cirruslib.utils import submit_batch_job
from cirruslib import Catalogs
from json import dumps
from os import getenv
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))


def lambda_handler(payload, context={}):
    logger.debug('Payload: %s' % json.dumps(payload))

    # if this is batch, output to stdout
    if not hasattr(context, "invoked_function_arn"):
        logger.addHandler(logging.StreamHandler())

    collections = payload.get('collections')
    index = payload.get('index', 'input_state')
    state = payload.get('state', 'FAILED')
    since = payload.get('since', None)
    limit = payload.get('limit', None)
    batch = payload.get('batch', False)
    catids = payload.get('catids', [])

    # if this is a lambda and batch is set
    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(payload, context.invoked_function_arn, name='rerun')
        return

    if len(catids) > 0:
        catalogs = Catalogs.from_catids(catids)
        logger.debug(f"Rerunning {len(catalogs.catalogs)} catalogs")
        catids = catalogs.process(replace=True)
        logger.info(f"{len(catids)} catalogs rerun")
        return catids

    catalogs = Catalogs.from_statedb(collections, state, since, index, limit=limit)

    logger.info(f"Fetched {len(catalogs.catalogs)} catalogs")
    catids = catalogs.process(replace=True)
    logger.info(f"{len(catids)} catalogs rerun")

    return catids
