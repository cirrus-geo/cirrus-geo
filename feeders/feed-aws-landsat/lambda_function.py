import boto3
import gzip
import itertools
import json
import logging
import requests
import sys
import uuid

from boto3utils import s3
from cirruslib.utils import submit_batch_job
from datetime import datetime
from os import getenv, path as op

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'INFO'))

SNS_TOPIC = getenv('CIRRUS_QUEUE_TOPIC_ARN')
LAMBDA_NAME = getenv('AWS_LAMBDA_FUNCTION_NAME')
CIRRUS_STACK = getenv('CIRRUS_STACK')
CATALOG_BUCKET = getenv('CIRRUS_CATALOG_BUCKET')
BASE_URL = "https://roda.sentinel-hub.com"

# clients
snsclient = boto3.client('sns')


PROCESS = {
    "description": "Convert Landsat MTL metadata to STAC and publish",
    "input_collections": ["landsat-8-l1-c1-aws"],
    "workflow": "publish-landsat",
    "output_options": {
        "path_template": "/${collection}/${landsat:wrs_path}/${landsat:wrs_row}/${year}/${month}/${id}",
        "collections": {
            "landsat-8-l1-c1": ".*"
        }
    },
    "functions": {
        "publish": {
            "public": True
        }
    }
}


def lambda_handler(payload, context={}):
    logger.info('Payload: %s' % json.dumps(payload))

    urls = []
    # process SNS topic arn:aws:sns:eu-central-1:214830741341:SentinelS2L2A if subscribed
    if 'Records' in payload:
        logger.info(f"{json.dumps(json.loads(payload['Records'][0]['Sns']['Message']))}")
        msg = json.loads(payload['Records'][0]['Sns']['Message'])['Records'][0]
        url = f"s3://{msg['s3']['bucket']['name']}/{msg['s3']['object']['key']}".rstrip('/index.html')
        bname = op.basename(url)
        # do not ingest real-time data
        if not bname.endswith('RT'):
            url = op.join(url, bname + '_MTL.txt')
            urls.append(url)
            logger.debug(f"URL: {url}")

    catids = []
    for url in urls:
        id = op.splitext(op.basename(url))[0].rstrip('_MTL')
        item = {
            'type': 'Feature',
            'id': id,
            'collection': 'landsat-8-l1-c1',
            'properties': {},
            'assets': {
                'txt': {
                    'href': url
                }
            }
        }
        catalog = {
            'type': 'FeatureCollection',
            'features': [item],
            'process': PROCESS
        }

        # feed to cirrus through SNS topic
        snsclient.publish(TopicArn=SNS_TOPIC, Message=json.dumps(catalog))
        logger.debug(f"Published {item['id']} to {SNS_TOPIC}")
        catids.append(item['id'])

    logger.info(f"Published {len(catids)} catalogs")
    return catids
