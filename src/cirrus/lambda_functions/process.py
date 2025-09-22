import contextlib
import json

from typing import Any

from cirrus.lib import utils
from cirrus.lib.enums import WFEventType
from cirrus.lib.errors import NoUrlError
from cirrus.lib.events import WorkflowEvent, WorkflowEventManager
from cirrus.lib.logging import defer, get_task_logger
from cirrus.lib.payload_manager import PayloadManager, PayloadManagers
from cirrus.lib.statedb import StateDB

utils.cold_start()

logger = get_task_logger("function.process", payload=())


def is_sqs_message(message):
    return message.get("eventSource") == "aws:sqs"


@WorkflowEventManager.with_wfem(logger=logger)
def lambda_handler(event, context, *, wfem: WorkflowEventManager):
    logger.debug(json.dumps(event))

    payload_managers: list[PayloadManager] = []
    failures: list[Any] = []
    messages: dict[str, list[dict[str, Any]]] = {}
    for message in utils.normalize_event(event):
        try:
            payload = utils.extract_record(message)
        except Exception as exc:
            logger.exception("Failed to extract record: %s", message)
            wfem.announce(
                WorkflowEvent(
                    event_type=WFEventType.RECORD_EXTRACT_FAILED,
                    payload_id="unknown",
                    isotimestamp=wfem.isotimestamp_now(),
                    payload_url=PayloadManager.upload_to_s3(message),
                    error=str(exc),
                ),
            )
            failures.append(message)
            continue

        # if the payload has a URL in it then we'll fetch it from S3
        with contextlib.suppress(NoUrlError):
            payload = utils.payload_from_s3(payload)

        logger.debug("payload: %s", defer(json.dumps, payload))

        try:
            payload_manager = PayloadManager(payload, set_id_if_missing=True)
        except Exception as exc:
            logger.exception(
                "Failed to instantiate a PayloadManager: %s",
                json.dumps(payload),
            )
            wfem.announce(
                WorkflowEvent(
                    event_type=WFEventType.NOT_A_PROCESS_PAYLOAD,
                    payload_id=payload.get("id", "unknown"),
                    isotimestamp=wfem.isotimestamp_now(),
                    payload_url=PayloadManager.upload_to_s3(payload),
                    error=str(exc),
                ),
            )
            failures.append(payload)
            continue

        payload_managers.append(payload_manager)

        if is_sqs_message(message):
            payload_id = payload_manager.payload["id"]
            try:
                messages[payload_id].append(message)
            except KeyError:
                messages[payload_id] = [message]

    processed_ids: set[str] = set()
    processed: dict[str, list[str]] = {"started": []}
    if len(payload_managers) > 0:
        processed = PayloadManagers(payload_managers, StateDB()).process(wfem)
        processed_ids = {pid for state in processed for pid in processed[state]}

    successful_sqs_messages = [
        message for _id in processed_ids for message in messages.pop(_id, [])
    ]
    failures.extend(messages.values())

    if failures:
        # If we have partial failure, then we want to delete all
        # successfully processed messages from the queue, so they
        # won't be reprocessed again. We don't need to do this if
        # we have no failures, as SQS will delete the messages for
        # us if we exit successfully.
        with utils.BatchHandler(
            utils.delete_from_queue_batch,
            batch_size=10,
        ) as handler:
            for message in successful_sqs_messages:
                handler.add(message)

        raise Exception("One or more payloads failed to process")

    return len(processed["started"])
