import argparse
import boto3
import json
import logging
import sys

from cirrus.lib2.statedb import StateDB
from cirrus.lib2.utils import submit_batch_job, batch_handler
from os import getenv


# envvars
SNS_TOPIC = getenv('CIRRUS_PROCESS_TOPIC_ARN')

# boto clients
SNS_CLIENT = boto3.client('sns')

# Cirrus state DB
statedb = StateDB()

# logging
logger = logging.getLogger("feeder.rerun")


def submit(payload_ids):
    with batch_handler(
        SNS_CLIENT.publish_batch,
        {'TopicArn': SNS_TOPIC},
        'PublishBatchRequestEntries',
    ) as handler:
        for payload_id in payload_ids:
            handler.add({'url': StateDB.get_payload_url(payload_id)})


def lambda_handler(payload, context={}):
    logger.debug('Payload: %s' % json.dumps(payload))

    collections = payload.get('collections')
    workflow = payload.get('workflow')
    state = payload.get('state', None)
    since = payload.get('since', None)
    limit = payload.get('limit', None)
    batch = payload.get('batch', False)
    error_begins_with = payload.get('error_begins_with', None)

    # if this is a lambda and batch is set
    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(payload, context.invoked_function_arn, name='rerun')
        return

    items = statedb.get_items(
        f"{collections}_{workflow}",
        state=state,
        since=since,
        limit=limit,
        error_begins_with=error_begins_with
    )

    nitems = len(items)
    logger.debug(f"Rerunning {nitems} payloads")

    submit((item['payload_id'] for item in items))

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
