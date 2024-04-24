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
        payload_id: str,
        payload_url: str = None,
        extra_message: dict = None,
    ) -> None:
        """
        Construct message payload and publish to WorkflowEventTopic.

        Args:
            event_type (WFEventType): the type of event which occurred
            payload_id (str): The ID of the payload.
            payload_url (str): URL of the ProcessPayload which triggered the event.
            extra_message (dict): dictionary of additional items to be placed into the
                                  SNS message body.
        """
        if self.event_publisher is None:
            return
        if payload_id is None:
            raise ValueError("Must specify a payload_id")

        message = {
            "event_type": event_type,
            "payload_url": payload_url,
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
        self: "WorkflowEventManager",
        payload_id: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.claim_processing(payload_id=payload_id, isotimestamp=isotimestamp)
        self.announce(
            WFEventType.CLAIMED_PROCESSING,
            payload_id=payload_id,
            payload_url=payload_url,
        )

    def started_processing(
        self: "WorkflowEventManager",
        payload_id: str,
        execution_arn: str,
        isotimestamp: str = None,
        payload_url: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_processing(payload_id, execution_arn, isotimestamp)
        self._write_timeseries_record(
            payload_id,
            state=StateEnum.PROCESSING,
            event_time=isotimestamp,
            execution_arn=execution_arn,
        )
        self.announce(
            WFEventType.STARTED_PROCESSING,
            payload_id=payload_id,
            payload_url=payload_url,
            extra_message={"execution_arn": execution_arn},
        )

    def skipping(
        self: "WorkflowEventManager",
        payload_id: str,
        state: StateEnum,
        payload_url: str = None,
    ):
        self.logger.warning("already in %s state: ", payload_id)
        self.announce(WFEventType(f"ALREADY_{state}"), payload_id, payload_url)

    def duplicated(
        self: "WorkflowEventManager", payload_id: str, payload_url: str = None
    ):
        self.logger.warning("duplicate payload_id dropped %s", payload_id)
        self.announce(WFEventType.DUPLICATE_ID_ENCOUNTERED, payload_id, payload_url)

    def failed(
        self: "WorkflowEventManager",
        payload_id: str,
        message: str = "",
        payload_url: str = None,
        execution_arn: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_failed(payload_id, message, execution_arn=execution_arn)
        if execution_arn:
            self._write_timeseries_record(
                payload_id, StateEnum.FAILED, isotimestamp, execution_arn
            )

        self.announce(
            WFEventType.FAILED,
            payload_id,
            payload_url,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def timed_out(
        self: "WorkflowEventManager",
        payload_id: str,
        message: str = "",
        payload_url: str = None,
        execution_arn: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_failed(
            payload_id,
            message,
            execution_arn=execution_arn,
            isotimestamp=isotimestamp,
        )
        if execution_arn:
            self._write_timeseries_record(
                payload_id, StateEnum.INVALID, isotimestamp, execution_arn
            )
        self.announce(
            WFEventType.TIMED_OUT,
            payload_id,
            payload_url,
            extra_message={"error": message, "execution_arn": execution_arn},
        )

    def succeeded(
        self: "WorkflowEventManager",
        payload_id: str,
        execution_arn: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_completed(
            payload_id, execution_arn=execution_arn, isotimestamp=isotimestamp
        )
        self._write_timeseries_record(
            payload_id, StateEnum.COMPLETED, isotimestamp, execution_arn
        )
        self.announce(WFEventType.SUCCEEDED, payload_id, payload_url)

    def invalid(
        self: "WorkflowEventManager",
        payload_id: str,
        error: str,
        execution_arn: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_invalid(payload_id, error, execution_arn, isotimestamp)
        if execution_arn:
            self._write_timeseries_record(
                payload_id, StateEnum.INVALID, isotimestamp, execution_arn
            )

        self.announce(
            WFEventType.INVALID,
            payload_id,
            payload_url,
            extra_message={"error": error, "execution_arn": execution_arn},
        )

    def aborted(
        self: "WorkflowEventManager",
        payload_id: str,
        execution_arn: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = datetime.now(timezone.utc).isoformat()
        self.statedb.set_aborted(payload_id, execution_arn=execution_arn)
        if execution_arn:
            self._write_timeseries_record(
                payload_id, StateEnum.ABORTED, isotimestamp, execution_arn
            )
        self.announce(
            WFEventType.ABORTED,
            payload_id,
            payload_url,
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
