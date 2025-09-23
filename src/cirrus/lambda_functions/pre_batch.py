import uuid

from os import getenv

from boto3utils import s3

from cirrus.lib.cirrus_payload import CirrusPayload
from cirrus.lib.logging import get_task_logger

# envvars
PAYLOAD_BUCKET = getenv("CIRRUS_PAYLOAD_BUCKET")


def lambda_handler(event, context):
    payload = CirrusPayload.from_event(event)
    logger = get_task_logger("task.pre-batch", payload=payload)

    url = f"s3://{PAYLOAD_BUCKET}/batch/{payload['id']}/{uuid.uuid1()}.json"
    url_out = url.replace(".json", "_out.json")

    try:
        # copy payload to s3
        s3().upload_json(payload, url)

        logger.debug("Uploaded payload to %s", url)
        return {"url": url, "url_out": url_out}
    except Exception as err:
        msg = f"pre-batch: failed pre processing batch job for ({err})"
        logger.exception(msg)
        raise Exception(msg) from err
