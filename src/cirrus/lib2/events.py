import json
import os
from logging import Logger, getLogger
from typing import Any, Dict, Tuple

import boto3

from .enums import StateEnum
from .statedb import StateDB
from .utils import SNSPublisher

logger = getLogger(__name__)


class WorkflowEventManager:
    """A class for managing payload state change events, including storage of
    state(dynamo), activity(timestream), and notifications of decisions and/or status
    changes (SNS)."""

    wf_event_topic_arn = os.getenv("CIRRUS_WF_EVENT_TOPIC_ARN", None)

    _message_template: Tuple[Tuple[str, Any]] = (
        ("payload_id", "some_id"),
        ("workflow_name", "some_workflow"),
        ("event_type", None),
        ("payload", None),
    )

    @classmethod
    def _get_message(cls, event_type: str, payload: Dict) -> Dict:
        message = dict(cls._message_template)
        message["event_type"] = event_type
        message["payload"] = payload
        return json.dumps(message)

    def __init__(
        self,
        logger: Logger = None,
        boto3_session: boto3.Session = None,
        statedb: StateDB = None,
    ):
        self.boto3_session = boto3_session if boto3_session else boto3.Session()
        self.event_publisher = (
            SNSPublisher(
                self.wf_event_topic_arn,
                logger=logger,
                boto3_session=self.boto3_session,
            )
            if self.wf_event_topic_arn
            else None
        )
        self.statedb = (
            statedb if statedb is not None else StateDB(session=self.boto3_session)
        )

    def announce(
        self,
        event_type: str,
        payload: dict = None,
        payload_id: str = None,
        extra_message: Dict = None,
    ) -> None:
        if self.event_publisher:
            message = self._get_message(event_type, payload)
            self.event_publisher.add(message)

    def claim_processing(self, payload):
        self.statedb.claim_processing(payload["id"])
        self.announce("CLAIMED_PROCESSING", payload)

    def started_processing(self, payload: Dict, execution_arn: str):
        self.statedb.set_processing(self["id"], execution_arn)
        self.announce("STARTED_PROCESSING", payload, execution_arn)

    def skipping(self, payload: Dict, state: StateEnum):
        self.logger.warning(f"already in {state} state: {payload['id']}")
        self.announce(f"ALREADY_{state}", payload)

    def duplicated(self, payload: Dict):
        self.logger.warning("duplicate payload_id dropped %s", payload["id"])
        self.announce("DUPLICATE_ID_ENCOUNTERED", payload)

    def failed(self, payload: Dict, message: str = ""):
        self.statedb.set_failed(self["id"], message)
        self.announce("FAILED", payload, extra_message=message)

    def succeeded(self, payload: Dict):
        self.announce("SUCCEEDED", payload)

    def invalid(self, payload: Dict):
        self.announce("INVALID", payload)

    def aborted(self, payload: Dict):
        self.announce("ABORTED", payload)

    def timed_out(self, payload: Dict):
        self.announce("TIMED_OUT", payload)
