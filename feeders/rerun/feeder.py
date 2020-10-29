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

# envvars
SNS_TOPIC = getenv('CIRRUS_QUEUE_TOPIC_ARN')

# clients
statedb = StateDB()
SNS_CLIENT = boto3.client('sns')

# logging
logger = logging.getLogger(f"{__name__}.rerun")



def submit(ids, process_update=None):
    payload = {
        "catids": ids
    }
    if process_update is not None:
        payload['process_update'] = process_update
    SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Message=json.dumps(payload))


def handler(payload, context={}):
    logger.debug('Payload: %s' % json.dumps(payload))

    collections = payload.get('collections')
    index = payload.get('index', 'input_state')
    state = payload.get('state', 'FAILED')
    since = payload.get('since', None)
    limit = payload.get('limit', None)
    batch = payload.get('batch', False)
    process_update = payload.get('process_update', None)
    catid_batch = 5

    # if this is a lambda and batch is set
    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(payload, context.invoked_function_arn, name='rerun')
        return

    items = statedb.get_items(collections, state, since, index, limit=limit)

    nitems = len(items)
    logger.debug(f"Rerunning {nitems} catalogs")

    catids = []
    for i, item in enumerate(items):
        catids.append(item['catid'])
        if (i % catid_batch) == 0:
            submit(catids, process_update=process_update)
            catids = []
        if (i % 1000) == 0:
            logger.debug(f"Queued {i} catalogs")
    if len(catids) > 0:
        submit(catids, process_update=process_update)

    return {
        "found": nitems
    }
