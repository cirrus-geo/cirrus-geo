import json
import os

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from logging import Logger, getLogger
from typing import Self

from .enums import StateEnum, WFEventType
from .eventdb import EventDB
from .statedb import StateDB
from .utils import PAYLOAD_ID_REGEX, SNSMessage, SNSPublisher, execution_url


@dataclass
class WorkflowEvent:
    event_type: WFEventType
    payload_id: str
    isotimestamp: str
    payload_url: str | None = None
    execution_arn: str | None = None
    error: str | None = None

    def serialize(self: Self) -> str:
        response = {x: y for (x, y) in vars(self).items() if y}
        if self.execution_arn:
            response["execution"] = execution_url(self.execution_arn)
            del response["execution_arn"]
        return json.dumps(response)

    @classmethod
    def from_message_str(cls: type[Self], message: str) -> Self:
        args = json.loads(message)
        execution = args.pop("execution", None)
        if execution is not None:
            args["execution_arn"] = execution.split("/")[-1]
        return cls(**args)

    def to_message(self: Self) -> SNSMessage:
        return SNSMessage(
            body=self.serialize(),
            attributes=self.sns_attributes(),
        )

    def sns_attributes(self: Self) -> dict[str, dict[str, str]]:
        attrs = {
            "event_type": {
                "DataType": "String",
                "StringValue": self.event_type,
            },
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
        return datetime.now(UTC).isoformat()

    def __init__(
        self: Self,
        logger: Logger | None = None,
        statedb: StateDB | None = None,
        eventdb: EventDB | None = None,
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

    def flush(self: Self):
        """Ensure any messages remaining in the batch buffer are sent."""
        if self.event_publisher:
            self.event_publisher.execute()

    def __enter__(self: Self):
        return self

    def __exit__(self: Self, et, ev, tb):
        self.flush()

    @classmethod
    def with_wfem(cls: type[Self], *wfem_args, **wfem_kwargs):
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

    def announce(self: Self, event: WorkflowEvent) -> None:
        """
        Construct message payload and publish to WorkflowEventTopic.

        Args:
            event (WorkflowEvent):
        """
        if self.event_publisher is None:
            return

        self.event_publisher.add(event.to_message())

    def claim_processing(
        self: Self,
        payload_id: str,
        execution_arn: str,
        payload_url: str | None = None,
        isotimestamp: str | None = None,
    ) -> str:
        if isotimestamp is None:
            isotimestamp = self.isotimestamp_now()

        resp = self.statedb.claim_processing(
            payload_id=payload_id,
            execution_arn=execution_arn,
            isotimestamp=isotimestamp,
        )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.CLAIMED_PROCESSING,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
            ),
        )

        return resp

    def started_processing(
        self: Self,
        payload_id: str,
        execution_arn: str,
        isotimestamp: str | None = None,
        payload_url: str | None = None,
    ):
        if isotimestamp is None:
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
            ),
        )

    def skipping(
        self: Self,
        payload_id: str,
        state: StateEnum,
        payload_url: str | None = None,
        message: str | None = "",
    ):
        self.logger.info(
            "Skipping %s already in %s state%s.",
            payload_id,
            state,
            f"({message})" if message else message,
        )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType(f"ALREADY_{state}"),
                payload_id=payload_id,
                isotimestamp=datetime.now(UTC).isoformat(),
                payload_url=payload_url,
            ),
        )

    def duplicated(
        self: Self,
        payload_id: str,
        payload_url: str | None = None,
    ):
        self.logger.warning("duplicate payload_id dropped %s", payload_id)
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.DUPLICATE_ID_ENCOUNTERED,
                payload_id=payload_id,
                isotimestamp=self.isotimestamp_now(),
                payload_url=payload_url,
            ),
        )

    def failed(
        self: Self,
        payload_id: str,
        message: str = "",
        payload_url: str | None = None,
        execution_arn: str | None = None,
        isotimestamp: str | None = None,
    ):
        if isotimestamp is None:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_failed(payload_id, message)
        if execution_arn:
            self._write_timeseries_record(
                payload_id,
                StateEnum.FAILED,
                isotimestamp,
                execution_arn,
            )

        self.announce(
            WorkflowEvent(
                event_type=WFEventType.FAILED,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                error=message,
                execution_arn=execution_arn,
            ),
        )

    def timed_out(
        self: Self,
        payload_id: str,
        message: str = "",
        payload_url: str | None = None,
        execution_arn: str | None = None,
        isotimestamp: str | None = None,
    ):
        if isotimestamp is None:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_failed(
            payload_id,
            message,
            isotimestamp=isotimestamp,
        )
        if execution_arn:
            self._write_timeseries_record(
                payload_id,
                StateEnum.INVALID,
                isotimestamp,
                execution_arn,
            )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.TIMED_OUT,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                error=message,
                execution_arn=execution_arn,
            ),
        )

    def succeeded(
        self: Self,
        payload_id: str,
        execution_arn: str,
        payload_url: str | None = None,
        isotimestamp: str | None = None,
    ):
        if isotimestamp is None:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_completed(
            payload_id,
            isotimestamp=isotimestamp,
        )
        self._write_timeseries_record(
            payload_id,
            StateEnum.COMPLETED,
            isotimestamp,
            execution_arn,
        )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.SUCCEEDED,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
            ),
        )

    def invalid(
        self: Self,
        payload_id: str,
        error: str,
        execution_arn: str,
        payload_url: str | None = None,
        isotimestamp: str | None = None,
    ):
        if isotimestamp is None:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_invalid(payload_id, error, isotimestamp)
        if execution_arn:
            self._write_timeseries_record(
                payload_id,
                StateEnum.INVALID,
                isotimestamp,
                execution_arn,
            )

        self.announce(
            WorkflowEvent(
                event_type=WFEventType.INVALID,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                error=error,
                execution_arn=execution_arn,
            ),
        )

    def aborted(
        self: Self,
        payload_id: str,
        execution_arn: str,
        payload_url: str | None = None,
        isotimestamp: str | None = None,
    ):
        if isotimestamp is None:
            isotimestamp = self.isotimestamp_now()
        self.statedb.set_aborted(payload_id)
        if execution_arn:
            self._write_timeseries_record(
                payload_id,
                StateEnum.ABORTED,
                isotimestamp,
                execution_arn,
            )
        self.announce(
            WorkflowEvent(
                event_type=WFEventType.ABORTED,
                payload_id=payload_id,
                isotimestamp=isotimestamp,
                payload_url=payload_url,
                execution_arn=execution_arn,
            ),
        )

    def _write_timeseries_record(
        self: Self,
        key: str,
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> None:
        if self.eventdb:
            self.eventdb.write_timeseries_record(key, state, event_time, execution_arn)
