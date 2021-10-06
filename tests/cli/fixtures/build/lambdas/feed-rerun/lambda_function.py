import argparse
import boto3
import json
import logging
import sys
import uuid

from boto3utils import s3
from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import submit_batch_job
from cirrus.lib.catalog import Catalogs
from json import dumps
from os import getenv
from traceback import format_exc

# envvars
SNS_TOPIC = getenv('CIRRUS_QUEUE_TOPIC_ARN')

# boto clients
SNS_CLIENT = boto3.client('sns')

# Cirrus state DB
statedb = StateDB()

# logging
logger = logging.getLogger("feeder.rerun")


def submit(ids, process_update=None):
    payload = {
        "catids": ids
    }
    if process_update is not None:
        payload['process_update'] = process_update
    SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Message=json.dumps(payload))


def lambda_handler(payload, context={}):
    logger.debug('Payload: %s' % json.dumps(payload))

    collections = payload.get('collections')
    workflow = payload.get('workflow')
    state = payload.get('state', None)
    since = payload.get('since', None)
    limit = payload.get('limit', None)
    batch = payload.get('batch', False)
    process_update = payload.get('process_update', None)
    catid_batch = 5

    # if this is a lambda and batch is set
    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(payload, context.invoked_function_arn, name='rerun')
        return

    items = statedb.get_items(f"{collections}_{workflow}", state=state, since=since, limit=limit)

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


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # argparse
    parser = argparse.ArgumentParser(description='feeder')
    parser.add_argument('payload', help='Payload file')
    args = parser.parse_args(sys.argv[1:])

    with open(args.payload) as f:
        payload = json.loads(f.read())
    lambda_handler(payload)
