import json
import os
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
from logging import Logger, getLogger
from typing import Dict

import boto3

from .enums import StateEnum, WFEventType
from .eventdb import EventDB
from .statedb import StateDB
from .utils import SNSPublisher

logger = getLogger(__name__)


class WorkflowEventManager:
    """A class for managing payload state change events, including storage of
    state (DynamoDB), activity (Timestream), and notifications of decisions and/or status
    changes (SNS)."""

    def __init__(
        self,
        logger: Logger = logger,
        boto3_session: boto3.Session = None,
        statedb: StateDB = None,
        eventdb: EventDB = None,
        batch_size: int = 10,
    ):
        self.logger = logger
        self._boto3_session = boto3_session if boto3_session else boto3.Session()
        wf_event_topic_arn = os.getenv("CIRRUS_WORKFLOW_EVENT_TOPIC_ARN")
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
        self.eventdb = (
            eventdb if eventdb is not None else EventDB(session=self._boto3_session)
        )

    def flush(self):
        if self.event_publisher:
            self.event_publisher.execute()

    @classmethod
    @contextmanager
    def handler(
        cls: "WorkflowEventManager", *args, **kwargs
    ) -> AbstractContextManager["WorkflowEventManager"]:
        wfem = cls(*args, **kwargs)
        try:
            yield wfem
        finally:
            wfem.flush()

    def announce(
        self,
        event_type: WFEventType,
        payload: dict = None,
        payload_id: str = None,
        extra_message: dict = None,
    ) -> None:
        """
        Construct message payload and publish to WorkflowEventTopic.

        Args:
            event_type (WFEventType): the type of event which occurred
            payload (dict): The ProcessPayload which triggered the event.
            payload_id (str): The ID of the payload.  Must match payload["id"] if that
                              exists / is  provided.
            extra_message (dict): dictionary of additional items to be placed into the
                                  SNS message body.
        """
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
                    "extra_message parameters must not include: "
                    + f"{','.join(message.keys())}."
                )
            message.update(extra_message)
        self.event_publisher.add(json.dumps(message))

    def claim_processing(self, payload: dict, isotimestamp: str = None):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.claim_processing(
            payload_id=payload["id"], isotimestamp=isotimestamp
        )
        self.announce(WFEventType.CLAIMED_PROCESSING, payload=payload)

    def started_processing(
        self, payload: dict, execution_arn: str, isotimestamp: str = None
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_processing(payload["id"], execution_arn, isotimestamp)
        self.write_timeseries_record(
            payload["id"],
            state=StateEnum.PROCESSING,
            event_time=isotimestamp,
            execution_arn=execution_arn,
        )
        self.announce(
            WFEventType.STARTED_PROCESSING,
            payload=payload,
            extra_message={"execution_arn": execution_arn},
        )

    def skipping(self, payload: dict, state: StateEnum):
        self.logger.warning(f"already in {state} state: {payload['id']}")
        self.announce(WFEventType(f"ALREADY_{state}"), payload)

    def duplicated(self, payload: dict):
        self.logger.warning("duplicate payload_id dropped %s", payload["id"])
        self.announce(WFEventType.DUPLICATE_ID_ENCOUNTERED, payload)

    def failed(
        self,
        payload: dict,
        message: str = "",
        execution_arn=None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_failed(payload["id"], message, execution_arn=execution_arn)
        if execution_arn:
            self.write_timeseries_record(
                payload["id"], StateEnum.FAILED, isotimestamp, execution_arn
            )

        self.announce(
            WFEventType.FAILED,
            payload,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def timed_out(
        self,
        payload: dict,
        message: str = "",
        execution_arn=None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_failed(
            payload["id"],
            message,
            execution_arn=execution_arn,
            isotimestamp=isotimestamp,
        )
        self.announce(
            WFEventType.TIMED_OUT,
            payload,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def succeeded(self, payload: dict, execution_arn: str, isotimestamp: str = None):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_completed(
            payload["id"], execution_arn=execution_arn, isotimestamp=isotimestamp
        )
        if execution_arn:
            self.write_timeseries_record(
                payload["id"], StateEnum.COMPLETED, isotimestamp, execution_arn
            )
        else:
            logger.debug("set completed called with no execution ARN")
        self.announce(WFEventType.SUCCEEDED, payload)

    def invalid(
        self, payload: dict, error: str, execution_arn: str, isotimestamp: str = None
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_invalid(payload["id"], error, execution_arn, isotimestamp)
        if execution_arn:
            self.write_timeseries_record(
                payload["id"], StateEnum.INVALID, isotimestamp, execution_arn
            )

        self.announce(
            WFEventType.INVALID,
            payload,
            extra_message={"error": error, "execution_arn": execution_arn},
        )

    def aborted(self, payload: dict, execution_arn: str, isotimestamp: str = None):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_aborted(payload["id"], execution_arn=execution_arn)
        if execution_arn:
            self.write_timeseries_record(
                payload["id"], StateEnum.ABORTED, isotimestamp, execution_arn
            )
        self.announce(
            WFEventType.ABORTED, payload, extra_message={"execution_arn": execution_arn}
        )

    def write_timeseries_record(
        self,
        key: Dict[str, str],
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> None:
        if self.eventdb:
            self.eventdb.write_timeseries_record(key, state, event_time, execution_arn)
