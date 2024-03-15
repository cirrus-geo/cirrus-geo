import json
import os
from logging import Logger, getLogger
from typing import Dict

import boto3

from .enums import StateEnum
from .statedb import StateDB
from .utils import SNSPublisher

logger = getLogger(__name__)


class WorkflowEventManager:
    """A class for managing payload state change events, including storage of
    state(dynamo), activity(timestream), and notifications of decisions and/or status
    changes (SNS)."""

    def __init__(
        self,
        logger: Logger = logger,
        boto3_session: boto3.Session = None,
        statedb: StateDB = None,
        batch_size: int = 10,
    ):
        self.logger = logger
        self._boto3_session = boto3_session if boto3_session else boto3.Session()
        wf_event_topic_arn = os.getenv("CIRRUS_WORKFLOW_EVENT_TOPIC_ARN", None)
        self.event_publisher = (
            SNSPublisher(
                wf_event_topic_arn,
                logger=logger,
                boto3_session=self._boto3_session,
                batch_size=batch_size,
            )
            if wf_event_topic_arn
            else None
        )
        self.statedb = (
            statedb if statedb is not None else StateDB(session=self._boto3_session)
        )

    def announce(
        self,
        event_type: str,
        payload: dict = None,
        payload_id: str = None,
        extra_message: Dict = None,
    ) -> None:
        """Construct message payload and publish to WorkflowEventTopic"""
        if self.event_publisher is None:
            return

        if payload is None:
            if payload_id is None:
                raise ValueError("must specify payload_id or payload")
        elif payload_id is None:
            payload_id = payload["id"]

        if payload is not None and payload["id"] != payload_id:
            raise ValueError(
                "payload_id and payload['id'] must match if both supplied."
            )
        message = {
            "event_type": event_type,
            "payload": payload,
            "payload_id": payload_id,
        }

        if extra_message:
            if not all(k not in message for k in extra_message):
                raise ValueError(
                    "extra_message parameters must not include "
                    "event_type, payload, or payload_id."
                )
            message.update(extra_message)
        self.event_publisher.add(json.dumps(message))

    def claim_processing(self, payload: dict):
        self.statedb.claim_processing(payload_id=payload["id"])
        self.announce("CLAIMED_PROCESSING", payload=payload)

    def started_processing(self, payload: dict, execution_arn: str):
        self.statedb.set_processing(payload["id"], execution_arn)
        self.announce(
            "STARTED_PROCESSING",
            payload=payload,
            extra_message={"execution_arn": execution_arn},
        )

    def skipping(self, payload: dict, state: StateEnum):
        self.logger.warning(f"already in {state} state: {payload['id']}")
        self.announce(f"ALREADY_{state}", payload)

    def duplicated(self, payload: dict):
        self.logger.warning("duplicate payload_id dropped %s", payload["id"])
        self.announce("DUPLICATE_ID_ENCOUNTERED", payload)

    def failed(self, payload: dict, message: str = "", execution_arn=None):
        self.statedb.set_failed(payload["id"], message, execution_arn=execution_arn)
        self.announce(
            "FAILED",
            payload,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def timed_out(self, payload: dict, message: str = "", execution_arn=None):
        self.statedb.set_failed(payload["id"], message, execution_arn=execution_arn)
        self.announce(
            "TIMED_OUT",
            payload,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def succeeded(self, payload_id: str, execution_arn: str):
        self.statedb.set_completed(payload_id, execution_arn=execution_arn)
        self.announce("SUCCEEDED", payload_id=payload_id)

    def invalid(self, payload: dict, error: str, execution_arn: str):
        self.statedb.set_invalid(payload["id"], error, execution_arn)

        self.announce(
            "INVALID",
            payload,
            extra_message={"error": error, "execution_arn": execution_arn},
        )

    def aborted(self, payload: dict, execution_arn: str):
        self.statedb.set_aborted(payload["id"], execution_arn=execution_arn)
        self.announce(
            "ABORTED", payload, extra_message={"execution_arn": execution_arn}
        )
