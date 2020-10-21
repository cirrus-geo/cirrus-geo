import uuid
from os import getenv

from boto3utils import s3
from cirruslib import Catalogs

# envvars
CATALOG_BUCKET = getenv('CIRRUS_CATALOG_BUCKET')


def lambda_handler(payload, context):
    catalog = Catalogs.from_payload(payload)[0]

    url = f"s3://{CATALOG_BUCKET}/batch/{catalog['id']}/{uuid.uuid1()}.json"

    try:
        # copy payload to s3
        s3().upload_json(catalog, url)

        catalog.logger.debug(f"Uploaded catalog to {url}")
        return {
            'url': url
        }
    except Exception as err:
        msg = f"pre-batch: failed pre processing batch job for {catalog['id']} ({err})"
        catalog.logger.error(msg, exc_info=True)
        raise Exception(msg) from err