import json

from cirrus.lib.errors import NoUrlError
from cirrus.lib.process_payload import ProcessPayload, ProcessPayloads
from cirrus.lib import utils
from cirrus.lib.logging import get_task_logger, defer


logger = get_task_logger('function.process', payload=tuple())


def lambda_handler(event, context):
    logger.debug(json.dumps(event))

    payloads = []
    failures = []
    messages = {}
    for message in utils.normalize_event(event):
        is_sqs_message = (
            True
            if 'eventSource' in message and message['eventSource'] == 'aws:sqs'
            else False
        )

        try:
            payload = utils.extract_record(message)
        except Exception as e:
            logger.exception('Failed to extract record: %s', json.dumps(message))
            if is_sqs_message:
                failures.append(message)

        # if the payload has a URL in it then we'll fetch it from S3
        try:
            payload = utils.payload_from_s3(payload)
        except NoUrlError:
            pass

        logger.debug('payload: %s', defer(json.dumps, payload))

        try:
            payloads.append(ProcessPayload(payload))
        except Exception:
            logger.exception('Failed to convert to ProcessPayload: %s', json.dumps(payload))
            if is_sqs_message:
                failures.append(payload)

        if is_sqs_message:
            try:
                messages[payload['id']].append(message)
            except KeyError:
                messages[payload['id']] = [message]

    if len(payloads) > 0:
        processed_ids = ProcessPayloads(payloads).process()

    successful = [
        message
        for _id in processed_ids
        for message in messages.pop(_id)
    ]
    failures += list(messages.values())

    if failures:
        # If we have partial failure, then we want to delete all
        # successfully processed messages from the queue, so they
        # won't be reprocessed again. We don't need to do this if
        # we have no failures, as SQS will delete the messages for
        # us if we exit successfully.
        for message in successful:
            try:
                utils.delete_from_queue(message)
            except Exception:
                logger.exception(
                    'Failed to delete message from queue: %s',
                    json.dumps(message),
                )

        raise Exception('One or more payloads failed to process')

    return len(processed_ids)
