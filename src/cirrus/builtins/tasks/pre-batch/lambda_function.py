import uuid
from os import getenv

from boto3utils import s3
from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.logging import get_task_logger

# envvars
PAYLOAD_BUCKET = getenv('CIRRUS_PAYLOAD_BUCKET')


def lambda_handler(event, context):
    payload = ProcessPayload.from_event(event)
    logger = get_task_logger("task.pre-batch", payload=payload)

    url = f"s3://{PAYLOAD_BUCKET}/batch/{payload['id']}/{uuid.uuid1()}.json"

    try:
        # copy payload to s3
        s3().upload_json(payload, url)

        logger.debug(f"Uploaded payload to {url}")
        return {
            'url': url
        }
    except Exception as err:
        msg = f"pre-batch: failed pre processing batch job for ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err
