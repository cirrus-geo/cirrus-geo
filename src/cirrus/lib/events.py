import json
import os
import uuid

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from logging import Logger, getLogger
from time import time
from typing import Any, Self

from .enums import StateEnum, WFEventType
from .eventdb import EventDB
from .statedb import StateDB
from .utils import (
    PAYLOAD_ID_REGEX,
    BatchHandler,
    SNSMessage,
    SNSPublisher,
    execution_url,
    get_client,
)


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
                "StringValue": str(self.event_type),
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
        Decorator to inject WorkflowEventManager (as `wfem`) into a function call, and
        flush upon exit.

        Args:
           See `help(WorkflowEventManager.__init__)`

        Returns:
           A function which runs the wrapped function in a WorkflowEventManager context,
           and passes in the WorkflowEventManager instance to be used within the the
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
        if self.event_publisher:
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
        self.statedb.set_processing(payload_id, isotimestamp)
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
        message: str = "",
    ):
        state2event = {
            StateEnum.INVALID: WFEventType.ALREADY_INVALID,
            StateEnum.PROCESSING: WFEventType.ALREADY_PROCESSING,
            StateEnum.CLAIMED: WFEventType.ALREADY_CLAIMED,
            StateEnum.COMPLETED: WFEventType.ALREADY_COMPLETED,
        }
        self.logger.info(
            "Skipping %s already in %s state%s.",
            payload_id,
            state,
            f"({message})" if message else message,
        )
        self.announce(
            WorkflowEvent(
                event_type=state2event[state],
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
                execution_arn=execution_arn,
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


class WorkflowMetrics(BatchHandler[WorkflowEvent]):
    """A class for surfacing workflow state changes to Cloudwatch
    Logs, and retrieving metrics from Cloudwatch Metrics."""

    def __init__(
        self: Self,
        logger: Logger | None = None,
        log_group_name: str | None = None,
        metric_name: str | None = None,
        batch_size: int = 10,
    ):
        super().__init__(batchable=self._send, batch_size=batch_size)
        self.logger = logger if logger is not None else getLogger(__name__)
        self.log_group_name = (
            log_group_name
            if log_group_name is not None
            else os.getenv("CIRRUS_WORKFLOW_LOG_GROUP", "")
        )
        self.metric_name = (
            metric_name
            if metric_name is not None
            else os.getenv("CIRRUS_WORKFLOW_METRIC_NAME", "")
        )
        self.sequence_token = None

        if self.log_group_name and self.metric_name:
            self.logs_client = get_client("logs")
            self.cw_client = get_client("cloudwatch")
            # Generate a UUID-based log stream name
            self.log_stream_name = f"workflow-{uuid.uuid4()}"
            # Create log stream if it does not exist
            try:
                self.logs_client.create_log_stream(
                    logGroupName=self.log_group_name,
                    logStreamName=self.log_stream_name,
                )
                self.logger.info("Created new log stream: %s", self.log_stream_name)
            except self.logs_client.exceptions.ResourceAlreadyExistsException:
                self.logger.info("Log stream already exists: %s", self.log_stream_name)
            # Retrieve sequence token
            response = self.logs_client.describe_log_streams(
                logGroupName=self.log_group_name,
                logStreamNamePrefix=self.log_stream_name,
            )
            log_streams = response["logStreams"]
            if not log_streams:
                raise Exception("Log stream not found after creation.")
            self.sequence_token = log_streams[0].get("uploadSequenceToken")
        else:
            self.logger.info(
                "Workflow metrics not configured, "
                "workflow state change metrics will not be recorded",
            )

    def enabled(self: Self) -> bool:
        return self.sequence_token is not None

    def _send(self: Self, batch: list[WorkflowEvent]) -> dict[str, Any]:
        # build log events
        params = {
            "logGroupName": self.log_group_name,
            "logStreamName": self.log_stream_name,
            "logEvents": self.prepare_batch(batch),
            "sequenceToken": self.sequence_token,
        }
        try:
            response = self.logs_client.put_log_events(**params)
            self.sequence_token = response["nextSequenceToken"]
            return response
        except self.logs_client.exceptions.InvalidSequenceTokenException as e:
            self.sequence_token = e.response["expectedSequenceToken"]
            # Retry once
            response = self.logs_client.put_log_events(**params)
            self.sequence_token = response["nextSequenceToken"]
            return response

    def add(self: Self, event: WorkflowEvent) -> None:
        if self.enabled():
            super().add(event)

    def build_log_event(
        self: Self,
        event: WorkflowEvent,
        timestamp: int,
    ) -> dict[str, Any]:
        if match := PAYLOAD_ID_REGEX.match(event.payload_id):
            workflow = match.group("workflow")
            source = match.group("collections")
        else:
            workflow = "unknown"
            source = "unknown"

        message = {
            "event": event,
            "workflow": workflow,
            "source": source,
            "execution_arn": event.execution_arn,
        }
        return {
            "timestamp": timestamp,
            "message": json.dumps(message),
        }

    def prepare_batch(self: Self, batch: list[WorkflowEvent]) -> list[dict[str, Any]]:
        timestamp = int(time() * 1000)
        return [
            self.build_log_event(event, timestamp + i) for i, event in enumerate(batch)
        ]

    def retrieve_metric_statistics(
        self: Self,
        start_time: datetime,
        end_time: datetime,
        period: int = 300,
        statistics: list[str] | None = None,
        dimensions: list[dict[str, str]] | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled():
            return None
        if statistics is None:
            statistics = ["SampleCount", "Average", "Sum", "Minimum", "Maximum"]
        if dimensions is None:
            dimensions = []

        return self.cw_client.get_metric_statistics(
            Namespace="log-cannon-metric-namespace",
            MetricName=self.metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=statistics,
        )
