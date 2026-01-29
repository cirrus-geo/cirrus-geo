import json
import os
import uuid
import warnings

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from logging import Logger, getLogger
from time import time
from typing import Any, Self, TypedDict

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


def date_formatter(granularity="s") -> Callable[[datetime], str]:
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

    This defaults to a batch_size of 1, to make all logs immediate.  This is because we
    can't guard against a lambda timing out an execution, and preventing us from
    sending the last batch of messages on exit."""

    def __init__(
        self: Self,
        logger: Logger | None = None,
        log_group_name: str = "",
        batch_size: int = 1,
    ):
        # TODO: Reconsider the batch_size if we get to making our
        #       event-emitting lambda handlers async, so we don't lose messages.
        super().__init__(batchable=self._send, batch_size=batch_size)
        self.logger = logger if logger is not None else getLogger(__name__)
        self.log_group_name = (
            log_group_name
            if len(log_group_name) > 0
            else os.getenv("CIRRUS_WORKFLOW_LOG_GROUP", "")
        )

        if self.log_group_name == "":
            self.logger.info(
                "WorkflowMetricLogger not configured, "
                "workflow state changes will not be logged",
            )
            return
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
        except self.logs_client.exceptions.ResourceNotFoundException as e:
            raise Exception(
                f"Log group {self.log_group_name} does not exist.",
            ) from e

    def enabled(self: Self) -> bool:
        return bool(self.log_group_name)

    def _send(self: Self, batch: list[WorkflowEvent]) -> dict[str, Any]:
        # build log events
        params = {
            "logGroupName": self.log_group_name,
            "logStreamName": self.log_stream_name,
            "logEvents": self.prepare_batch(batch),
        }

        return self.logs_client.put_log_events(**params)

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


class WorkflowMetric(TypedDict):
    """Summary of workflow events for period starting at `period` and running for the
    given `interval` (in seconds)"""

    period: str
    interval: int
    events: dict[str, int]


class WorkflowMetricSeries[WorkflowMetric](TypedDict):
    """`metrics` is a list of WorkflowMetric summaries for the named `workflow`"""

    workflow: str
    metrics: list[WorkflowMetric]


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
    ):
        """

        Args:
           logger (Logger | None): Logger instance to use. If None is provided, the
                default logger is used.
            metric_namespace (str): Namespace of the CloudWatch metric.
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
        self._enabled = metric_namespace is not None and self.metric_namespace != ""
        if self._enabled:
            resp = self.cw_client.list_metrics(Namespace=self.metric_namespace)
            self._metrics = {metric["MetricName"] for metric in resp["Metrics"]}
            if self.metric_some_workflows not in self._metrics or (
                self.metric_all_workflows not in self._metrics
            ):
                self.logger.warning(
                    "No metrics found in namespace (%s).  "
                    "This is OK if the deployment hasn't reun any workflows yet",
                    self.metric_namespace,
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
        formatter: Callable[[datetime], str] | None = None,
    ) -> list[WorkflowMetricSeries]:
        """
        Retrieve metrics from CloudWatch for specific workflows.  Aggregated by event,
        for each workflow in `workflows`.

        NOTE: This makes an API call for each workflow, so this method is much more
              costly than `aggregated_by event_type`, if you are interested in all
              workflows running in the deployment.

        Args:
            event_types (list[WFEventType]): List of workflow event types to filter.
            workflows (list[str]): List of workflow names to filter.
            start_time (datetime): Start of the time window.
            end_time (datetime): End of the time window.
            period (int): Granularity in seconds.

        Returns:
            list[dict[str, int]]: List of metric data dictionaries retrieved.
        """
        if event_types is None:
            event_types = list(WFEventType)
        if formatter is None:
            formatter = date_formatter()
        cstats: dict[str, dict[datetime, dict[str, int]]] = {
            workflow: defaultdict(
                lambda: dict.fromkeys([str(e) for e in event_types], 0),
            )
            for workflow in workflows
        }
        for workflow in workflows:
            mdqs = [
                {
                    "Id": str(event_type).lower()
                    + "___"
                    + workflow.lower().replace("-", "_"),
                    "MetricStat": {
                        "Metric": {
                            "Namespace": self.metric_namespace,
                            "MetricName": self.metric_some_workflows,
                            "Dimensions": [
                                {
                                    "Name": "event",
                                    "Value": str(event_type),
                                },
                                {
                                    "Name": "workflow",
                                    "Value": workflow,
                                },
                            ],
                        },
                        "Period": period,
                        "Stat": WorkflowMetricReader._agg_statistic,
                    },
                    "Label": str(event_type),
                    "ReturnData": False,
                }
                for event_type in event_types
            ] + [
                {
                    "Id": self.metric_some_workflows,
                    "Expression": "FILL(METRICS(), 0)",
                    "Label": "ZFILL",
                    "ReturnData": True,
                    "Period": period,
                },
            ]
            resp = self.cw_client.get_metric_data(
                MetricDataQueries=mdqs,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampAscending",
            )
            for mdr in resp["MetricDataResults"]:
                for timestamp, values in zip(
                    mdr["Timestamps"],
                    mdr["Values"],
                    strict=True,
                ):
                    eventtype = mdr["Label"].replace("ZFILL ", "")
                    cstats[workflow][timestamp][eventtype] = int(values)
        retvals = []
        for wf, wfstats in cstats.items():
            wfmetrics: WorkflowMetricSeries = {"workflow": wf, "metrics": []}
            for timestamp, metrics in sorted(wfstats.items(), key=lambda x: x[0]):
                wfm: WorkflowMetric = {
                    "period": formatter(timestamp),
                    "interval": period,
                    "events": dict(metrics),
                }
                wfmetrics["metrics"].append(wfm)

            retvals.append(wfmetrics)

        return retvals

    def aggregated_by_event_type(
        self,
        start_time: datetime,
        end_time: datetime,
        period: int = 3600,
        event_types: list[WFEventType] | None = None,
        formatter: Callable[[datetime], str] | None = None,
    ) -> list[WorkflowMetric]:
        """
        Retrieve metrics from CloudWatch for all workflows.

        Args:
            start_time (datetime): Start of the time window.
            end_time (datetime): End of the time window.
            period (int): Granularity in seconds.
            event_types (list[WFEventType]): List of workflow event types to filter.
            formatter (Callable[[datetime], str]: different requests to this function
                require different formatting, and

        Returns:
            list[WorkflowMetric]: List of metric statistics dictionaries retrieved.

        """
        if event_types is None:
            event_types = list(WFEventType)
        if formatter is None:
            formatter = date_formatter()
        mdqs = [
            {
                "Id": str(event_type).lower(),
                "MetricStat": {
                    "Metric": {
                        "Namespace": self.metric_namespace,
                        "MetricName": WorkflowMetricReader.metric_all_workflows,
                        "Dimensions": [
                            {
                                "Name": "event",
                                "Value": str(event_type),
                            },
                        ],
                    },
                    "Period": period,
                    "Stat": WorkflowMetricReader._agg_statistic,
                },
                "Label": str(event_type),
                "ReturnData": False,
            }
            for event_type in event_types
        ] + [
            {
                "Id": self.metric_all_workflows,
                "Expression": "FILL(METRICS(), 0)",
                "Label": "ZFILL",
                "ReturnData": True,
                "Period": period,
            },
        ]

        resp = self.cw_client.get_metric_data(
            MetricDataQueries=mdqs,
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampAscending",
        )

        cstats: dict[datetime, dict[str, int]] = defaultdict(
            lambda: defaultdict(lambda: 0),
        )
        for mdr in resp["MetricDataResults"]:
            for timestamp, value in zip(
                mdr["Timestamps"],
                mdr["Values"],
                strict=True,
            ):
                eventtype = mdr["Label"].replace("ZFILL ", "")
                cstats[timestamp][eventtype] = int(value)
        retval = []
        for timestamp, metrics in sorted(cstats.items(), key=lambda x: x[0]):
            wfm: WorkflowMetric = {
                "period": formatter(timestamp),
                "interval": period,
                "events": dict(metrics),
            }
            retval.append(wfm)

        return retval


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
