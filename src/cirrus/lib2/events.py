import json
import os
from datetime import datetime, timezone
from functools import wraps
from logging import Logger, getLogger
from typing import Callable, Dict

import boto3

from .enums import StateEnum, WFEventType
from .eventdb import EventDB
from .statedb import StateDB
from .utils import SNSPublisher


class WorkflowEventManager:
    """A class for managing payload state change events, including:
    1. storage of state (DynamoDB)
    2. storage of data for workflow metrics (Timestream)
    3. notifications of Cirrus decisions and/or workflow status changes (SNS).

    Other than `announce`, which is used for announcement of malformed
    payloads/messages, the public functions here are aimed for use in the `process` and
    `update-state` lambdas.
    """

    def __init__(
        self: "WorkflowEventManager",
        logger: Logger = None,
        statedb: StateDB = None,
        eventdb: EventDB = None,
        batch_size: int = 10,
    ):
        self.logger = logger if logger is not None else getLogger(__name__)
        self._boto3_session = boto3.Session()
        wf_event_topic_arn = os.getenv("CIRRUS_WORKFLOW_EVENT_TOPIC_ARN")
        self.event_publisher = (
            SNSPublisher(
                wf_event_topic_arn,
                logger=self.logger,
                boto3_session=self._boto3_session,
                batch_size=batch_size,
            )
            if wf_event_topic_arn
            else None
        )
        self.statedb = statedb if statedb is not None else StateDB.get_singleton()
        self.eventdb = (
            eventdb if eventdb is not None else EventDB(session=self._boto3_session)
        )

    def flush(self: "WorkflowEventManager"):
        """Ensure any messages remaining in the batch buffer are sent."""
        if self.event_publisher:
            self.event_publisher.execute()

    def __enter__(self: "WorkflowEventManager"):
        return self

    def __exit__(self: "WorkflowEventManager", et, ev, tb):
        self.flush()

    @classmethod
    def with_wfem(cls: "WorkflowEventManager", *wfem_args, **wfem_kwargs):
        """
        Decorator to inject WorkflowEvenManager (as `wfem`) into a function call, and
        flush upon exit.

        Args:
           See `help(WorkflowEvenManager.__init__)`

        Returns:
           A function which runs the wrapped function in a WorkflowEvenManager context,
           and passes in the WorkflowEvenManager instance to be used within the the
           function
        """

        def decorator(function: Callable):
            @wraps(function)
            def wrap_function(*args, **kwargs):
                with cls(*wfem_args, **wfem_kwargs) as wfem:
                    return function(*args, **kwargs, wfem=wfem)

            return wrap_function

        return decorator

    def announce(
        self: "WorkflowEventManager",
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
                "payload_id and payload['id'] must match, if both supplied."
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
        self.event_publisher.add(
            message=json.dumps(message),
            message_attrs={
                "event_type": {"DataType": "String", "StringValue": event_type}
            },
        )

    def claim_processing(
        self: "WorkflowEventManager", payload: dict, isotimestamp: str = None
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.claim_processing(
            payload_id=payload["id"], isotimestamp=isotimestamp
        )
        self.announce(WFEventType.CLAIMED_PROCESSING, payload=payload)

    def started_processing(
        self: "WorkflowEventManager",
        payload: dict,
        execution_arn: str,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_processing(payload["id"], execution_arn, isotimestamp)
        self._write_timeseries_record(
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

    def skipping(self: "WorkflowEventManager", payload: dict, state: StateEnum):
        self.logger.warning("already in %s state: ", payload["id"])
        self.announce(WFEventType(f"ALREADY_{state}"), payload)

    def duplicated(self: "WorkflowEventManager", payload: dict):
        self.logger.warning("duplicate payload_id dropped %s", payload["id"])
        self.announce(WFEventType.DUPLICATE_ID_ENCOUNTERED, payload)

    def failed(
        self: "WorkflowEventManager",
        payload: dict,
        message: str = "",
        execution_arn=None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_failed(payload["id"], message, execution_arn=execution_arn)
        if execution_arn:
            self._write_timeseries_record(
                payload["id"], StateEnum.FAILED, isotimestamp, execution_arn
            )

        self.announce(
            WFEventType.FAILED,
            payload,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def timed_out(
        self: "WorkflowEventManager",
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
        if execution_arn:
            self._write_timeseries_record(
                payload["id"], StateEnum.INVALID, isotimestamp, execution_arn
            )
        self.announce(
            WFEventType.TIMED_OUT,
            payload,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def succeeded(
        self: "WorkflowEventManager",
        payload: dict,
        execution_arn: str,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_completed(
            payload["id"], execution_arn=execution_arn, isotimestamp=isotimestamp
        )
        self._write_timeseries_record(
            payload["id"], StateEnum.COMPLETED, isotimestamp, execution_arn
        )
        self.announce(WFEventType.SUCCEEDED, payload)

    def invalid(
        self: "WorkflowEventManager",
        payload: dict,
        error: str,
        execution_arn: str,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_invalid(payload["id"], error, execution_arn, isotimestamp)
        if execution_arn:
            self._write_timeseries_record(
                payload["id"], StateEnum.INVALID, isotimestamp, execution_arn
            )

        self.announce(
            WFEventType.INVALID,
            payload,
            extra_message={"error": error, "execution_arn": execution_arn},
        )

    def aborted(
        self: "WorkflowEventManager",
        payload: dict,
        execution_arn: str,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_aborted(payload["id"], execution_arn=execution_arn)
        if execution_arn:
            self._write_timeseries_record(
                payload["id"], StateEnum.ABORTED, isotimestamp, execution_arn
            )
        self.announce(
            WFEventType.ABORTED,
            payload,
            extra_message={
                "error": "none, aborted by user",
                "execution_arn": execution_arn,
            },
        )

    def _write_timeseries_record(
        self: "WorkflowEventManager",
        key: Dict[str, str],
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> None:
        if self.eventdb:
            self.eventdb.write_timeseries_record(key, state, event_time, execution_arn)
