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

BATCH_CLIENT = boto3.client('batch')

'''
This feeder accepts a list of URLs to tileInfo.json files, or an SNS topic providing a list of update files

subscribe to this SNS for new scenes: arn:aws:sns:eu-central-1:214830741341:SentinelS2L2A

Example payloads:

Payload of URLs to tileInfo.json files
{
    "urls": [
        "https://roda.sentinel-hub.com/key/tileInfo.json",
        "https://roda.sentinel-hub.com/key/tileInfo.json"
    ]
}

OR

define `latest_inventory` to get the complete most recent inventory and kick off 
batch processes to process all the inventory files

{
    'latest_inventory": {

    }
}

OR

an s3 URL to an array of inventory files which will extract the tileInfo.json files
and process them. This inherently assumes a batch process. A Lambda will timeout with
even a single inventory file
{
    "inventory_files": [
        "<s3-url>"
    ]
}

'''

PROCESS = {
    "description": "Convert Original Sentinel-2 metadata to STAC and publish",
    "input_collections": ["sentinel-s2-l2a-aws"],
    "workflow": "publish-sentinel",
    "output_options": {
        "path_template": "/${collection}/${sentinel:utm_zone}/${sentinel:latitude_band}/${sentinel:grid_square}/${year}/${month}/${id}",
        "collections": {
            "sentinel-s2-l1c": ".*L1C",
            "sentinel-s2-l2a": ".*L2A"
        }
    },
    "functions": {
        "publish": {
            "public": True
        }
    }
}


def submit_inventory_batch_jobs(inventory_url, lambda_arn, batch_size: int=10, max_batches: int=-1):
    urls = []
    n = 0
    for url in s3().latest_inventory_files(inventory_url):
        urls.append(url)
        if (len(urls) % batch_size) == 0:
            submit_batch_job({'inventory_files': urls}, lambda_arn)
            urls = []
            n += 1
            if max_batches > 0 and n > max_batches:
                break
    if len(urls) > 0:
        submit_batch_job({'inventory_files': urls}, lambda_arn)
        n += 1
    logger.info(f"Submitted {n} jobs")
    return n


def lambda_handler(payload, context={}):
    logger.info('Payload: %s' % json.dumps(payload))

    # process SNS topic arn:aws:sns:eu-central-1:214830741341:SentinelS2L2A if subscribed
    if 'Records' in payload:
        # TODO - determine input collection from payload
        paths = [t['path'] for t in json.loads(payload['Records'][0]['Sns']['Message'])['tiles']]
        payload = {
            'urls': [f"{BASE_URL}/sentinel-s2-l2a/{p}/tileInfo.json" for p in paths]
        }

    # get latest inventory and spawn batch(es)
    latest_inventory = payload.get('latest_inventory', None)
    if latest_inventory is not None:
        return submit_inventory_batch_jobs(**latest_inventory)

    # process inventory files (assumes this is batch!)
    inventory_files = payload.get('inventory_files', None)
    if inventory_files:
        urls = []
        for f in inventory_files:
            filename = s3().download(f, path='/tmp')
            with gzip.open(filename, 'rt') as f:
                for line in f:
                    if 'tileInfo.json' in line:
                        parts = line.split(',')
                        bucket = parts[0].strip('"')
                        key = parts[1].strip('"')
                        urls.append(f"{BASE_URL}/{bucket}/{key}")
        logger.info(f"Extracted {len(urls)} URLs from {len(inventory_files)}")
        payload['urls'] = urls

    catids = []
    if 'urls' in payload:
        replace = payload.pop('replace', False)
        PROCESS.update({'replace': replace})
        for i, url in enumerate(payload['urls']):
            # populating catalog with bare minimum
            key = s3().urlparse(s3().https_to_s3(url))['key']
            id = '-'.join(op.dirname(key).split('/')[1:])
            # TODO - determime input collection from url
            item = {
                'type': 'Feature',
                'id': id,
                'collection': 'sentinel-s2-l2a-aws',
                'properties': {},
                'assets': {
                    'json': {
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
            client = boto3.client('sns')
            logger.debug(f"Published {json.dumps(catalog)}")
            client.publish(TopicArn=SNS_TOPIC, Message=json.dumps(catalog))
            if ((i+1) % 250) == 0:
                logger.debug(f"Published {i+1} catalogs to {SNS_TOPIC}")

            catids.append(item['id'])

        logger.info(f"Published {len(catids)} catalogs")

    return catids
