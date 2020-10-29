import uuid
from os import getenv

from boto3utils import s3
from cirruslib import Catalog, get_task_logger

# envvars
CATALOG_BUCKET = getenv('CIRRUS_CATALOG_BUCKET')


def handler(payload, context):
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger(f"{__name__}.pre-batch", catalog=catalog)

    url = f"s3://{CATALOG_BUCKET}/batch/{catalog['id']}/{uuid.uuid1()}.json"

    try:
        # copy payload to s3
        s3().upload_json(catalog, url)

        logger.debug(f"Uploaded catalog to {url}")
        return {
            'url': url
        }
    except Exception as err:
        msg = f"pre-batch: failed pre processing batch job for ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err