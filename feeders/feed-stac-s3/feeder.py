import argparse
import boto3
import json
import logging
import os
import requests
import sys

from cirruslib.transfer import get_s3_session


# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(os.getenv('CIRRUS_LOG_LEVEL', 'INFO'))


# Process configuration
'''
{
    "s3urls": ["s3://bucket/key"],
    "suffix": "json",
    "process": {
        "collection": "<collectionId>",
        "workflow": "mirror"
        "tasks": {
            "copy-assets": {
                ...
            }
        }
    }
}
'''


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
            client = boto3.client('sns')
            SNS_TOPIC = os.getenv('CIRRUS_QUEUE_TOPIC_ARN')
            client.publish(TopicArn=SNS_TOPIC, Message=json.dumps(catalog))
            if (num % 500) == 0:
                logger.debug(f"Added {num+1} items to Cirrus")
            num+=1

    logger.info(f"Published {num} catalogs")
    return num


def parse_args(args):
    desc = 'feeder'
    dhf = argparse.ArgumentDefaultsHelpFormatter
    parser = argparse.ArgumentParser(description=desc, formatter_class=dhf)
    parser.add_argument('s3url', help='S3 URL to crawl for STAC JSON files')
    parser.add_argument('--source_profile', help='Name of AWS profile to use to get data', default=None)
    #parser.add_argument('--workdir', help='Work directory', default='')
    #parser.add_argument('--queue', help='Name of Cirrus Queue Lambda', default=None)
    #parser.add_argument('--output_url', help='S3 URL prefix for uploading data', default=None)
    
    #parser.add_argument('--cirrus_profile', help='Name of AWS profile to use for queuing to Cirrus', default=None)

    return vars(parser.parse_args(args))


def cli():
    handler(parse_args(sys.argv[1:]))


if __name__ == "__main__":
    cli()
