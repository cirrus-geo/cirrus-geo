import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from logging import Logger, getLogger
from typing import Optional

from .enums import StateEnum, WFEventType
from .eventdb import EventDB
from .statedb import StateDB
from .utils import PAYLOAD_ID_REGEX, SNSPublisher, execution_url


@dataclass
class WorkflowEvent:
    event_type: WFEventType
    payload_id: str
    isotimestamp: str
    payload_url: Optional[str] = None
    execution_arn: Optional[str] = None
    error: Optional[str] = None

    def serialize(self):
        response = {x: y for (x, y) in vars(self).items() if y}
        if self.execution_arn:
            response["execution"] = execution_url(self.execution_arn)
            del response["execution_arn"]
        return json.dumps(response)

    @classmethod
    def from_message(cls, message: str) -> "WorkflowEvent":
        args = json.loads(message)
        execution = args.pop("execution", None)
        if execution is not None:
            args["execution_arn"] = execution.split("/")[-1]
        return cls(**args)

    def sns_attributes(self) -> dict[str, dict[str, str]]:
        attrs = {
            "event_type": {
                "DataType": "String",
                "StringValue": self.event_type,
            }
        }

        if match := PAYLOAD_ID_REGEX.match(self.payload_id):
            attrs["workflow"] = {
                "DataType": "String",
                "StringValue": match.group("workflow"),
            }
            attrs["collections"] = {
                "DataType": "String",
                "StringValue": match.group("collections"),
            }
        if self.error is not None:
            attrs["error"] = {"DataType": "String", "StringValue": self.error}
        return attrs


class WorkflowEventManager:
    """A class for managing payload state change events, including:
    1. storage of state (DynamoDB)
    2. storage of data for workflow metrics (Timestream)
    3. notifications of Cirrus decisions and/or workflow status changes (SNS).

    Other than `announce`, which is used for announcement of malformed
    payloads/messages, the public functions here are aimed for use in the `process` and
    `update-state` lambdas.
    """

    @staticmethod
    def isotimestamp_now():
        return datetime.now(timezone.utc).isoformat()

    def __init__(
        self: "WorkflowEventManager",
        logger: Logger = None,
        statedb: StateDB = None,
        eventdb: EventDB = None,
        batch_size: int = 10,
    ):
        self.logger = logger if logger is not None else getLogger(__name__)
        wf_event_topic_arn = os.getenv("CIRRUS_WORKFLOW_EVENT_TOPIC_ARN")
        self.event_publisher = (
            SNSPublisher(
                wf_event_topic_arn,
                logger=self.logger,
                batch_size=batch_size,
            )
            if wf_event_topic_arn
            else None
        )
        self.statedb = statedb if statedb is not None else StateDB()
        self.eventdb = eventdb if eventdb is not None else EventDB()

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

    def announce(self: "WorkflowEventManager", message: WorkflowEvent) -> None:
        """
        Construct message payload and publish to WorkflowEventTopic.

        Args:
            message (WorkflowEvent):
        """
        if self.event_publisher is None:
            return

        self.event_publisher.add(
            message=message.serialize(), message_attrs=message.sns_attributes()
        )

    def claim_processing(
        self: "WorkflowEventManager",
        payload_id: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = self.isotimestamp_now()
        self.statedb.claim_processing(payload_id=payload_id, isotimestamp=isotimestamp)
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.CLAIMED_PROCESSING,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
            )
        )

    def started_processing(
        self: "WorkflowEventManager",
        payload_id: str,
        execution_arn: str,
        isotimestamp: str = None,
        payload_url: str = None,
    ):
        if not isotimestamp:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_processing(payload_id, execution_arn, isotimestamp)
        self._write_timeseries_record(
            payload_id,
            state=StateEnum.PROCESSING,
            event_time=isotimestamp,
            execution_arn=execution_arn,
        )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.STARTED_PROCESSING,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                execution_arn=execution_arn,
            )
        )

    def skipping(
        self: "WorkflowEventManager",
        payload_id: str,
        state: StateEnum,
        payload_url: str = None,
    ):
        self.logger.info("Skipping %s already in %s state: ", payload_id, state)
        self.announce(
            WorkflowEvent(
                event_type=WFEventType(f"ALREADY_{state}"),
                payload_id=payload_id,
                isotimestamp=datetime.now(timezone.utc).isoformat(),
                payload_url=payload_url,
            )
        )

    def duplicated(
        self: "WorkflowEventManager", payload_id: str, payload_url: str = None
    ):
        self.logger.warning("duplicate payload_id dropped %s", payload_id)
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.DUPLICATE_ID_ENCOUNTERED,
                payload_id=payload_id,
                isotimestamp=self.isotimestamp_now(),
                payload_url=payload_url,
            )
        )

    def failed(
        self: "WorkflowEventManager",
        payload_id: str,
        message: str = "",
        payload_url: str = None,
        execution_arn: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_failed(payload_id, message, execution_arn=execution_arn)
        if execution_arn:
            self._write_timeseries_record(
                payload_id, StateEnum.FAILED, isotimestamp, execution_arn
            )

        self.announce(
            WorkflowEvent(
                event_type=WFEventType.FAILED,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                error=message,
                execution_arn=execution_arn,
            )
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
            isotimestamp = self.isotimestamp_now()
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
            WorkflowEvent(
                event_type=WFEventType.TIMED_OUT,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                error=message,
                execution_arn=execution_arn,
            )
        )

    def succeeded(
        self: "WorkflowEventManager",
        payload_id: str,
        execution_arn: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_completed(
            payload_id, execution_arn=execution_arn, isotimestamp=isotimestamp
        )
        self._write_timeseries_record(
            payload_id, StateEnum.COMPLETED, isotimestamp, execution_arn
        )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.SUCCEEDED,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
            )
        )

    def invalid(
        self: "WorkflowEventManager",
        payload_id: str,
        error: str,
        execution_arn: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_invalid(payload_id, error, execution_arn, isotimestamp)
        if execution_arn:
            self._write_timeseries_record(
                payload_id, StateEnum.INVALID, isotimestamp, execution_arn
            )

        self.announce(
            WorkflowEvent(
                event_type=WFEventType.INVALID,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                error=error,
                execution_arn=execution_arn,
            )
        )

    def aborted(
        self: "WorkflowEventManager",
        payload_id: str,
        execution_arn: str,
        payload_url: str = None,
        isotimestamp: str = None,
    ):
        if not isotimestamp:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_aborted(payload_id, execution_arn=execution_arn)
        if execution_arn:
            self._write_timeseries_record(
                payload_id, StateEnum.ABORTED, isotimestamp, execution_arn
            )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.ABORTED,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                execution_arn=execution_arn,
            )
        )

    def _write_timeseries_record(
        self: "WorkflowEventManager",
        key: dict[str, str],
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> None:
        if self.eventdb:
            self.eventdb.write_timeseries_record(key, state, event_time, execution_arn)
