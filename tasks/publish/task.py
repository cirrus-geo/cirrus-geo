import boto3
import json
import os.path as op
import re
import requests

from cirruslib import Catalog, StateDB
from cirruslib.transfer import get_s3_session
from logging import getLogger
from os import getenv

# envvars
DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET')
# DEPRECATED - additional topics
PUBLISH_TOPICS = getenv('CIRRUS_PUBLISH_SNS', None)

# clients
statedb = StateDB()


def handler(payload, context):
    catalog = Catalog.from_payload(payload)

    config = catalog['process']['tasks'].get('publish', {})
    public = config.get('public', False)
    # additional SNS topics to publish to
    topics = config.get('sns', [])

    # these are the URLs to the canonical records on s3
    s3urls = []

    try:
        catalog.logger.debug("Publishing items to s3 and SNS")

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
        msg = f"publish: failed publishing output items ({err})"
        catalog.logger.error(msg, exc_info=True)
        raise Exception(msg) from err

    try:
        # update processing in table
        statedb.set_completed(catalog['id'], s3urls)
    except Exception as err:
        msg = f"publish: failed setting as complete ({err})"
        catalog.logger.error(msg, exc_info=True)
        raise Exception(msg) from err        

    return catalog