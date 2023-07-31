import json

from cirrus.lib2 import utils
from cirrus.lib2.errors import NoUrlError
from cirrus.lib2.logging import defer, get_task_logger
from cirrus.lib2.process_payload import ProcessPayload, ProcessPayloads

logger = get_task_logger("function.process", payload=tuple())


def is_sqs_message(message):
    return message.get("eventSource") == "aws:sqs"


def lambda_handler(event, context):
    logger.debug(json.dumps(event))

    payloads = []
    failures = []
    messages = {}
    for message in utils.normalize_event(event):

        try:
            payload = utils.extract_record(message)
        except Exception:
            logger.exception("Failed to extract record: %s", json.dumps(message))
            failures.append(message)
            continue

        # if the payload has a URL in it then we'll fetch it from S3
        try:
            payload = utils.payload_from_s3(payload)
        except NoUrlError:
            pass

        logger.debug("payload: %s", defer(json.dumps, payload))

        try:
            payload = ProcessPayload(payload, set_id_if_missing=True)
        except Exception:
            logger.exception(
                "Failed to convert to ProcessPayload: %s", json.dumps(payload)
            )
            failures.append(payload)
            continue

        payloads.append(payload)

        if is_sqs_message(message):
            payload_id = payload["id"]
            try:
                messages[payload_id].append(message)
            except KeyError:
                messages[payload_id] = [message]

    processed_ids = set()
    processed = {"started": []}
    if len(payloads) > 0:
        processed = ProcessPayloads(payloads).process()
        processed_ids = {pid for state in processed.keys() for pid in processed[state]}

    successful_sqs_messages = [
        message for _id in processed_ids for message in messages.pop(_id, [])
    ]
    failures += list(messages.values())

    if failures:
        # If we have partial failure, then we want to delete all
        # successfully processed messages from the queue, so they
        # won't be reprocessed again. We don't need to do this if
        # we have no failures, as SQS will delete the messages for
        # us if we exit successfully.
        with utils.batch_handler(
            utils.delete_from_queue_batch,
            {},
            "messages",
            batch_size=10,
        ) as handler:
            for message in successful_sqs_messages:
                handler.add(message)

        raise Exception("One or more payloads failed to process")

    return len(processed["started"])
