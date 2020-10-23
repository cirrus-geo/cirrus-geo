import argparse
import boto3
import datetime
import json
import logging
import math
import os
import requests
import sys
import time
import uuid

import os.path as op

from boto3utils import s3
from copy import deepcopy
from cirruslib.utils import submit_batch_job
from dateutil.parser import parse
from pystac import Catalog


# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(os.getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

# envvars
SNS_TOPIC = os.getenv('CIRRUS_QUEUE_TOPIC_ARN')
CATALOG_BUCKET = os.getenv('CIRRUS_CATALOG_BUCKET')
CIRRUS_STACK = os.getenv('CIRRUS_STACK')

# AWS clients
BATCH_CLIENT = boto3.client('batch')
SNS_CLIENT = boto3.client('sns')
    

def handler(event, context={}):
    # if this is batch, output to stdout
    if not hasattr(context, "invoked_function_arn"):
        logger.addHandler(logging.StreamHandler())

    logger.debug('Event: %s' % json.dumps(event))

    # parse input
    url = event.get('url')
    batch = event.get('batch', False)
    process = event['process']

    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(event, context.invoked_function_arn, definition='lambda-as-batch', name='feed-stac-crawl')
        return

    cat = Catalog.from_file(url)

    for item in cat.get_all_items():
        payload = {
            'type': 'FeatureCollection',
            'features': [item.to_dict()],
            'process': process
        }
        SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Message=json.dumps(payload))
