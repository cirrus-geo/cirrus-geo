import boto3
import json
import logging
import requests

from boto3utils import s3
from boto3.dynamodb.conditions import Key
from cirruslib  import stac
from json import dumps
from os import getenv, path as op
from shutil import rmtree
from tempfile import mkdtemp
from traceback import format_exc
from urllib.parse import urljoin


# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

# envvars
PUBLISH_TOPIC = getenv('CIRRUS_PUBLISH_TOPIC_ARN', None)

REGION = getenv('AWS_REGION', 'us-west-2')
CONSOLE_URL = f"https://{REGION}.console.aws.amazon.com/"

snsclient = boto3.client('sns')


def lambda_handler(event, context):
    logger.debug('Event: %s' % json.dumps(event))
    
    # check if collection and if so, add to Cirrus
    if 'extent' in event:
        # add to static catalog
        stac.add_collection(event)

        # send to Cirrus Publish SNS
        response = snsclient.publish(TopicArn=PUBLISH_TOPIC, Message=json.dumps(event))
        logger.debug(f"SNS Publish response: {json.dumps(response)}")