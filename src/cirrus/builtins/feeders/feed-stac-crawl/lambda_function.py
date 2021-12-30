import argparse
import boto3
import json
import logging
import os
import sys

from cirrus.lib.utils import submit_batch_job
from pystac import Catalog

# envvars
SNS_TOPIC = os.getenv('CIRRUS_PROCESS_TOPIC_ARN')

# clients
SNS_CLIENT = boto3.client('sns')

# logging
logger = logging.getLogger("feeder.stac-crawl")


def lambda_handler(event, context={}):
    logger.debug('Event: %s' % json.dumps(event))

    # parse input
    url = event.get('url')
    batch = event.get('batch', False)
    process = event['process']

    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(
            event,
            context.invoked_function_arn,
            definition='lambda-as-batch',
            name='feed-stac-crawl',
        )
        return

    cat = Catalog.from_file(url)

    for item in cat.get_all_items():
        payload = {
            'type': 'FeatureCollection',
            'features': [item.to_dict()],
            'process': process
        }
        SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Message=json.dumps(payload))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # argparse
    parser = argparse.ArgumentParser(description='feeder')
    parser.add_argument('payload', help='Payload file')
    args = parser.parse_args(sys.argv[1:])

    with open(args.payload) as f:
        payload = json.loads(f.read())
    lambda_handler(payload)
