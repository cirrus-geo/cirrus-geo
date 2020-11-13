import argparse
import boto3
import json
import logging
import os
import requests
import sys

from cirruslib.transfer import get_s3_session

# envvars
SNS_TOPIC = os.getenv('CIRRUS_QUEUE_TOPIC_ARN')

# boto clients
SNS_CLIENT = boto3.client('sns')

# logging
logger = logging.getLogger(f"{__name__}.stac-s3")


def handler(event, context={}):
    logger.debug('Event: %s' % json.dumps(event))

    # parse input
    s3urls = event['s3urls']
    suffix = event.get('suffix', 'json')

    # process block required
    process = event['process']

    num = 0
    for s3url in s3urls:
        s3session = get_s3_session(s3url=s3url)
        logger.info(f"Searching {s3url} for STAC Items")
        # TODO - s3.find() will not work with requester pays needed for listing
        for filename in s3session.find(s3url, suffix=suffix):
            item = s3session.read_json(filename)

            # verify this is a STAC Item before continuing
            if item.get('type', '') != 'Feature':
                continue

            # update relative urls, assuming assets have relative paths for now
            for a in item['assets']:
                item['assets'][a]['href'] = os.path.join(os.path.dirname(filename), item['assets'][a]['href'])

            # create catalog
            catalog = {
                'type': 'FeatureCollection',
                'collections': [],
                'features': [item],
                'process': process
            }

            # feed to cirrus through SNS topic

            SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Message=json.dumps(catalog))
            if (num % 500) == 0:
                logger.debug(f"Added {num+1} items to Cirrus")
            num+=1

    logger.info(f"Published {num} catalogs")
    return num


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # argparse
    parser = argparse.ArgumentParser(description='feeder')
    parser.add_argument('payload', help='Payload file')
    args = parser.parse_args(sys.argv[1:])

    with open(args.payload) as f:
        payload = json.loads(f.read())
    handler(payload)
