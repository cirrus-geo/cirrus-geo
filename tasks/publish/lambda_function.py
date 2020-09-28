import boto3
import json
import os.path as op
import re
import requests

from cirruslib import Catalog, Catalogs, StateDB
from cirruslib.transfer import get_s3_session
from logging import getLogger
from os import getenv
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'INFO'))

# envvars
DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET')
# DEPRECATED - additional topics
PUBLISH_TOPICS = getenv('CIRRUS_PUBLISH_SNS', None)

# clients
statedb = StateDB()


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    catalog = Catalogs.from_payload(payload)[0]

    logger.debug('Catalog: %s' % json.dumps(catalog))

    config = catalog['process']['tasks'].get('publish', {})
    public = config.get('public', False)
    # additional SNS topics to publish to
    topics = config.get('sns', [])

    # these are the URLs to the canonical records on s3
    s3urls = []

    try:
        # publish to s3
        s3urls = catalog.publish_to_s3(DATA_BUCKET, public=public)

        # publish to Cirrus SNS publish topic
        catalog.publish_to_sns()

        # Deprecated additional topics
        if PUBLISH_TOPICS:
            for t in PUBLISH_TOPICS.split(','):
                catalog.publish_to_sns(t)

        for t in topics:
            catalog.publish_to_sns(t)
    except Exception as err:
        msg = f"publish: failed publishing output items in {catalog['id']} ({err})"
        logger.error(msg)
        logger.error(format_exc())
        raise Exception(msg) from err

    try:
        # update processing in table
        statedb.set_completed(catalog['id'], s3urls)
        logger.info(f"publish: completed processing {catalog['id']}")
    except Exception as err:
        msg = f"publish: failed setting {catalog['id']} as complete ({err})"
        logger.error(msg)
        logger.error(format_exc())
        raise Exception(msg) from err        

    return catalog