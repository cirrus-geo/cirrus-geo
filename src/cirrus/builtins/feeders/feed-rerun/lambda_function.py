import argparse
import boto3
import json
import logging
import sys

from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import submit_batch_job
from os import getenv


# envvars
SNS_TOPIC = getenv('CIRRUS_PROCESS_TOPIC_ARN')

# boto clients
SNS_CLIENT = boto3.client('sns')

# Cirrus state DB
statedb = StateDB()

# logging
logger = logging.getLogger("feeder.rerun")


def submit(ids, process_update=None):
    payload = {
        "payload_ids": ids
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
    payload_id_batch = 5

    # if this is a lambda and batch is set
    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(payload, context.invoked_function_arn, name='rerun')
        return

    items = statedb.get_items(
        f"{collections}_{workflow}",
        state=state,
        since=since,
        limit=limit,
    )

    nitems = len(items)
    logger.debug(f"Rerunning {nitems} payloads")

    payload_ids = []
    for i, item in enumerate(items):
        payload_ids.append(item['payload_id'])
        if (i % payload_id_batch) == 0:
            submit(payload_ids, process_update=process_update)
            payload_ids = []
        if (i % 1000) == 0:
            logger.debug(f"Queued {i} payloads")
    if len(payload_ids) > 0:
        submit(payload_ids, process_update=process_update)

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
