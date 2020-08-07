import boto3
import json
import logging
import os

from boto3utils import s3
from cirruslib import Catalogs
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(os.getenv('CIRRUS_LOG_LEVEL', 'INFO'))


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    catalogs = Catalogs.from_payload(payload)

    catids = catalogs.process()

    return catids
