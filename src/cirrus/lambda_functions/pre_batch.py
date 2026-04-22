from cirrus.lib.cirrus_payload import CirrusPayload
from cirrus.lib.logging import CirrusLoggerAdapter
from cirrus.lib.payload_bucket import PayloadBucket

logger = CirrusLoggerAdapter("function.pre-batch")


def lambda_handler(event, context):
    payload_bucket = PayloadBucket.from_env()
    payload = CirrusPayload.from_event(event)

    logger.reset_extra(
        payload=payload,
        aws_request_id=context.aws_request_id,
    )

    try:
        # copy payload to s3
        url = payload_bucket.upload_batch_payload(payload)
    except Exception as err:
        msg = f"pre-batch: failed pre processing batch job for ({err})"
        logger.exception(msg)
        raise Exception(msg) from err

    logger.debug("Uploaded payload to %s", url)
    return {"url": url, "url_out": url.replace(".json", "_out.json")}
