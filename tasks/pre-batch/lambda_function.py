import json
import logging
import uuid

from boto3utils import s3
from cirruslib import Catalogs
from json import dumps
from os import getenv, path as op
from shutil import rmtree
from tempfile import mkdtemp
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

CATALOG_BUCKET = getenv('CIRRUS_CATALOG_BUCKET')


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    catalog = Catalogs.from_payload(payload)[0]

    url = f"s3://{CATALOG_BUCKET}/batch/{catalog['id']}/{uuid.uuid1()}.json"

    try:
        # copy payload to s3
        s3().upload_json(catalog, url)

        logger.debug(f"Uploaded {catalog['id']} to {url}")
        logger.info(f"Completed pre processing batch job for {catalog['id']}")
        return {
            'url': url
        }
    except Exception as err:
        msg = f"pre-batch: failed pre processing batch job for {catalog['id']} ({err})"
        logger.error(msg)
        logger.error(format_exc())
        raise Exception(msg) from err