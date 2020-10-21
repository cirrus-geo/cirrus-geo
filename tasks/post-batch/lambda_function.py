import json
import logging

from boto3utils import s3
from json import dumps
from os import getenv, path as op
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    # catalog URL
    url = payload['Parameters']['url'].replace('.json', '_out.json')

    try:
        # copy payload from s3
        catalog = s3().read_json(url)
        return catalog
    except Exception as err:
        msg = f"post-batch: failed post processing batch job for {url} ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err
