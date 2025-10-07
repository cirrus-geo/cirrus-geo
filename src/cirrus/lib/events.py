import json
import os
import uuid
import warnings

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import wraps
from logging import Logger, getLogger
from time import time
from typing import Any, Self

from botocore.exceptions import ParamValidationError

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
    parse_since,
)


def date_formatter(granularity="s") -> Callable:
    """Return string representation of the given datetime, truncated to the specified
    granularity.  Timezone handling is deferred to the datetime library behavior.

    Args:
       granularity (str): 'd'|'h'|'m', defaulting to 'm'
                          'd' - date only (YYYY-MM-DD)
                          'h' - hour (YYYY-MM-DDTHH:00:00)
                          'm' - minute (YYYY-MM-DDTHH:MM:00)
                          's' - minute (YYYY-MM-DDTHH:MM:SS.uuuuu)
    """
    return {
        "d": lambda dt: dt.date().isoformat(),
        "h": lambda dt: dt.replace(minute=0, second=0, microsecond=0).isoformat(),
        "m": lambda dt: dt.replace(second=0, microsecond=0).isoformat(),
        "s": lambda dt: dt.isoformat(),
    }[granularity]


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

    def log_metric_format(self: Self) -> dict[str, Any]:
        if match := PAYLOAD_ID_REGEX.match(self.payload_id):
            workflow = match.group("workflow")
            source = match.group("collections")
        else:
            workflow = "could not parse"
            source = str(self.payload_id)

        return {
            "event": str(self.event_type),
            "workflow": workflow,
            "source": source,
            "execution_arn": self.execution_arn,
        }

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


class WorkflowMetricLogger(BatchHandler[WorkflowEvent]):
    """A class for surfacing workflow state changes to Cloudwatch
    Logs, and retrieving metrics from Cloudwatch Metrics.

    This defaults to a batch_size of 1, to make all logs immediate."""

    def __init__(
        self: Self,
        logger: Logger | None = None,
        log_group_name: str = "",
        batch_size: int = 1,
    ):
        super().__init__(batchable=self._send, batch_size=batch_size)
        self.logger = logger if logger is not None else getLogger(__name__)
        self.log_group_name = (
            log_group_name
            if len(log_group_name) > 0
            else os.getenv("CIRRUS_WORKFLOW_LOG_GROUP", "")
        )
        self.sequence_token = None

        if self.log_group_name != "":
            self.logs_client = get_client("logs")
            # Generate a UUID-based log stream name
            self.log_stream_name = f"workflow-metrics-{uuid.uuid4()}"
            # Create log stream if it does not exist
            self.logger.debug(
                "Creating log stream %s, in log group %s",
                self.log_stream_name,
                self.log_group_name,
            )
            try:
                self.logs_client.create_log_stream(
                    logGroupName=self.log_group_name,
                    logStreamName=self.log_stream_name,
                )
                self.logger.info("Created new log stream: %s", self.log_stream_name)
            except self.logs_client.exceptions.ResourceAlreadyExistsException:
                self.logger.info("Log stream already exists: %s", self.log_stream_name)
            except self.logs_client.exceptions.ResourceNotFoundException as e:
                raise Exception(
                    f"Log group {self.log_group_name} does not exist.",
                ) from e
            # Retrieve sequence token
            response = self.logs_client.describe_log_streams(
                logGroupName=self.log_group_name,
                logStreamNamePrefix=self.log_stream_name,
            )
            self.log_stream = (
                response["logStreams"][0] if len(response["logStreams"]) > 0 else None
            )
            if self.log_stream is None:
                raise Exception("Log stream not found after attempted creation.")

        else:
            self.logger.info(
                "WorkflowMetricLogger not configured, "
                "workflow state changes will not be logged",
            )

    def enabled(self: Self) -> bool:
        return bool(self.log_group_name) and self.log_stream is not None

    def _send(self: Self, batch: list[WorkflowEvent]) -> dict[str, Any]:
        # build log events
        params = {
            "logGroupName": self.log_group_name,
            "logStreamName": self.log_stream_name,
            "logEvents": self.prepare_batch(batch),
        }
        if self.sequence_token is not None:
            params["sequenceToken"] = self.sequence_token

        try:
            response = self.logs_client.put_log_events(**params)
            self.sequence_token = response["nextSequenceToken"]
            return response
        except ParamValidationError as e:
            self.sequence_token = e.response["expectedSequenceToken"]
            # Retry once
            response = self.logs_client.put_log_events(**params)
            self.sequence_token = response["nextSequenceToken"]
            return response

    def add(self: Self, event: WorkflowEvent) -> None:
        if self.enabled():
            super().add(event)

    def prepare_batch(self: Self, batch: list[WorkflowEvent]) -> list[dict[str, Any]]:
        timestamp = int(time() * 1000)

        return [
            {
                "message": json.dumps(event.log_metric_format()),
                "timestamp": timestamp + i,
            }
            for i, event in enumerate(batch)
        ]


class WorkflowMetricReader:
    """
    A class for retrieving workflow metrics from CloudWatch.
    """

    _agg_statistic = "SampleCount"
    metric_some_workflows = "a_workflow_by_event"
    metric_all_workflows = "all_workflows_by_event"

    def __init__(
        self,
        logger: Logger | None = None,
        metric_namespace: str = "",
        log_group_name: str = "",
    ):
        """

        Args:
           logger (Logger | None): Logger instance to use. If None is provided, the
                default logger is used.
            metric_namespace (str): Namespace of the CloudWatch metric.
                If "", then use the CIRRUS_WORKFLOW_METRIC_NAMESPACE from environment.

            log_group_name (str): Log Group associated with the CloudWatch metrics.
                If "", then use the CIRRUS_WORKFLOW_METRIC_NAMESPACE from environment.
        """

        self.cw_client = get_client("cloudwatch")
        self.logger = logger if logger is not None else getLogger(__name__)
        self.metric_namespace = (
            metric_namespace
            if metric_namespace != ""
            else os.getenv(
                "CIRRUS_WORKFLOW_METRIC_NAMESPACE",
                "",
            )
        )
        self.log_group_name = (
            log_group_name
            if log_group_name != ""
            else os.getenv("CIRRUS_WORKFLOW_LOG_GROUP", "")
        )
        self._enabled = metric_namespace is not None and self.metric_namespace != ""
        if self._enabled:
            resp = get_client("logs").describe_metric_filters(
                logGroupName=self.log_group_name,
            )
            list_of_metrics = resp.get("metricFilters", [])
            self._metrics = {
                metric["metricTransformations"][0]["metricName"]
                for metric in list_of_metrics
            }
            if self.metric_some_workflows not in self._metrics or (
                self.metric_all_workflows not in self._metrics
            ):
                raise ValueError(
                    f"No metrics found in namespace {self.metric_namespace}",
                )

    def enabled(self) -> bool:
        return self._enabled

    def aggregated_for_specified_workflows(
        self,
        workflows: list[str],
        start_time: datetime,
        end_time: datetime,
        period: int = 3600,
        event_types: list[WFEventType] | None = None,
        statistics: list[str] | None = None,
        formatter: Callable[[datetime], str] | None = None,
    ) -> list[dict[str, str | dict[str, dict[str, float]]]]:
        """
        Retrieve metric statistics from CloudWatch.

        Args:
            event_types (list[WFEventType]): List of workflow event types to filter.
            workflows (list[str]): List of workflow names to filter.
            start_time (datetime): Start of the time window.
            end_time (datetime): End of the time window.
            period (int): Granularity in seconds.
            statistics (list[str]): List of statistics to retrieve.

        Returns:
            list[dict[str, Any]]: List of metric statistics dictionaries retrieved.
        """
        if statistics is None:
            statistics = [WorkflowMetricReader._agg_statistic]
        if event_types is None:
            event_types = list(WFEventType)
        if formatter is None:
            formatter = date_formatter()
        delta = timedelta(seconds=period)
        dates = [
            start_time + i * delta
            for i in range(int((end_time - start_time).total_seconds() / period))
        ]
        fcstats: dict[datetime, dict[str, dict[str, float]]] = {
            d.replace(second=0, microsecond=0): {
                e: dict.fromkeys(statistics, 0.0) for e in event_types
            }
            for d in dates
        }

        for workflow in workflows:
            for event_type in event_types:
                resp = self.cw_client.get_metric_statistics(
                    Namespace=self.metric_namespace,
                    MetricName=self.metric_some_workflows,
                    Dimensions=[
                        {"Name": "event", "Value": str(event_type)},
                        {"Name": "workflow", "Value": workflow},
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=period,
                    Statistics=statistics,
                )
                for datapoint in resp["Datapoints"]:
                    tstamp = datapoint["Timestamp"]
                    for statistic in statistics:
                        stat = datapoint[statistic]
                        fcstats[tstamp][str(event_type)][statistic] += stat
        # TODO: break this out by workflow, maybe
        return [
            {"period": formatter(k), "events": dict(v)}
            for k, v in sorted(fcstats.items(), key=lambda x: x[0])
        ]

    def aggregated_by_event_type(
        self,
        start_time: datetime,
        end_time: datetime,
        period: int = 3600,
        event_types: list[WFEventType] | None = None,
        statistics: list[str] | None = None,
        formatter: Callable[[datetime], str] | None = None,
    ) -> list[dict[str, str | dict[str, dict[str, float]]]]:
        """
        Retrieve metric statistics from CloudWatch.

        Args:
            event_types (list[WFEventType]): List of workflow event types to filter.
            start_time (datetime): Start of the time window.
            end_time (datetime): End of the time window.
            period (int): Granularity in seconds.
            statistics (list[str]): List of statistics to retrieve.

        Returns:
            list[dict[str, Any]]: List of metric statistics dictionaries retrieved.

        """
        if statistics is None:
            statistics = [WorkflowMetricReader._agg_statistic]
        if event_types is None:
            event_types = list(WFEventType)
        if formatter is None:
            formatter = date_formatter()
        delta = timedelta(seconds=period)
        dates = [
            start_time + i * delta
            for i in range(int((end_time - start_time).total_seconds() / period))
        ]
        fcstats: dict[datetime, dict[str, dict[str, float]]] = {
            d.replace(second=0, microsecond=0): {
                str(e): dict.fromkeys(statistics, 0.0) for e in event_types
            }
            for d in dates
        }
        for event_type in event_types:
            resp = self.cw_client.get_metric_statistics(
                Namespace=self.metric_namespace,
                MetricName=self.metric_all_workflows,
                Dimensions=[
                    {"Name": "event", "Value": str(event_type)},
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=period,
                Statistics=statistics,
            )
            for datapoint in resp["Datapoints"]:
                tstamp = datapoint["Timestamp"]
                for statistic in statistics:
                    stat = datapoint[statistic]
                    try:
                        fcstats[tstamp][str(event_type)][statistic] += stat
                    except KeyError as ke:
                        self.logger.error(
                            "KeyError accessing fcstats[%s][%s][%s]: %s",
                            tstamp,
                            str(event_type),
                            statistic,
                            ke,
                        )
                        self.logger.error(
                            "fcstats keys",
                            list(fcstats.keys()),
                        )
                        raise ke

        return [
            {"period": formatter(k), "events": dict(v)}
            for k, v in sorted(fcstats.items(), key=lambda x: x[0])
        ]

    def query_hour(
        self,
        start: int,
        end: int,
    ) -> list[dict[str, str | dict[str, dict[str, float]]]]:
        """
        Query CloudWatch metrics for a specific hour range.
        """
        now = datetime.now(UTC)
        end_time = now - timedelta(hours=end)
        start_time = now - timedelta(hours=start)
        return self.aggregated_by_event_type(
            start_time=start_time,
            end_time=end_time,
            period=3600,
            formatter=date_formatter(),
        )

    def query_by_bin_and_duration(
        self,
        bin_size: str,
        duration: str,
    ) -> list[dict[str, str | dict[str, dict[str, float]]]]:
        """
        Query CloudWatch metrics for a given bin size and duration.
        bin_size: e.g. '1d', '1h'
        duration: e.g. '30d', '7d'
        """
        delta = parse_since(duration)

        end_time = datetime.now(UTC)
        start_time = end_time - delta

        period = int(parse_since(bin_size).total_seconds())

        return self.aggregated_by_event_type(
            start_time=start_time,
            end_time=end_time,
            period=period,
            formatter=date_formatter(),
        )


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
        metric_logger: WorkflowMetricLogger | None = None,
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
        if self.eventdb.enabled():
            warnings.warn(
                "`EventDB` is deprecated, use `WorkflowMetricLogger` instead",
                DeprecationWarning,
                stacklevel=2,
            )
        self.metric_logger = (
            WorkflowMetricLogger(logger=self.logger)
            if metric_logger is None
            else metric_logger
        )

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
        Construct message payload and publish (if enabled) to:
             1. WorkflowEventTopic (SNS)
             2. WorkflowMetricsLogger (CloudWatch)

        Args:
            event (WorkflowEvent):
        """
        if self.event_publisher:
            self.event_publisher.add(event.to_message())
        if self.metric_logger.enabled():
            self.metric_logger.add(event)

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
