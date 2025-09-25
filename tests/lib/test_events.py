import contextlib
import os

from datetime import UTC, datetime, timedelta
from pprint import pformat
from time import sleep

import pytest

from moto import mock_aws

from cirrus.lib.events import (
    WFEventType,
    WorkflowEvent,
    WorkflowMetricLogger,
    WorkflowMetricReader,
)
from cirrus.lib.utils import get_client


def make_event():
    return WorkflowEvent(
        event_type=WFEventType.SUCCEEDED,
        payload_id="somesource/workflow-copier/someitem",
        isotimestamp="2024-01-01T00:00:00Z",
    )


@mock_aws
def test_workflow_metric_logger_and_and_send():
    log_group_name = "ircwaves-test-20250903"
    # Setup environment variables for log group and metric name
    os.environ["CIRRUS_WORKFLOW_LOG_GROUP"] = log_group_name

    # Create log group and log stream using boto3 client
    logs_client = get_client("logs")
    logs_client.create_log_group(logGroupName=log_group_name)
    # The logger will create a unique log stream, so we don't create it here

    metric_logger = WorkflowMetricLogger(log_group_name=log_group_name, batch_size=1)
    assert metric_logger.enabled()
    event = make_event()
    metric_logger.add(event)
    metric_logger.add(event)

    # Check that a log stream was created and log events were put
    events = logs_client.get_log_events(
        logGroupName=log_group_name,
        logStreamName=metric_logger.log_stream_name,
    )
    assert len(events["events"]) == 2


@pytest.mark.skip(reason="moto does not support CloudWatch Log Metric Filters")
@mock_aws
def test_workflow_metric_reader_get_statistics():
    """Test the WorkflowMetricReader by setting up metric filters and logging some
    events.  Then retrieve statistics and verify the results.  This test can only be run
    against real AWS because moto does not fully support CloudWatch Log Metric Filters.
    Comment out the @mock_aws decorator to run against real AWS by using the following
    snippet:

        uv run python -c '
        import tests.lib.test_events as te ;
        te.test_workflow_metric_reader_get_statistics()
        '

    Note: this test will create a log group and metric filters, if they do not exist.
    """
    log_group_name = "cirrus-deployment"

    # Create log group and log stream using boto3 client
    logs_client = get_client("logs")
    with contextlib.suppress(BaseException):
        logs_client.create_log_group(logGroupName=log_group_name)

    # Setup environment variables for log group and metric name
    os.environ["CIRRUS_WORKFLOW_LOG_GROUP"] = log_group_name

    metric_namespace = "cirrus-deployment"
    metric_name = "all_workflows_by_event"
    # Setup environment variables for metric name and namespace
    with contextlib.suppress(BaseException):
        logs_client.put_metric_filter(
            logGroupName=log_group_name,
            filterName=metric_name,
            filterPattern='{$.event = "*"}',
            metricTransformations=[
                {
                    "metricName": metric_name,
                    "metricNamespace": metric_namespace,
                    "metricValue": "1",
                    "dimensions": {"event": "$.event"},
                },
            ],
        )

    metric_name = "a_workflow_by_event"
    with contextlib.suppress(BaseException):
        logs_client.put_metric_filter(
            logGroupName=log_group_name,
            filterName=metric_name,
            filterPattern='{($.event = "*") && ($.workflow = "*")}',
            metricTransformations=[
                {
                    "metricName": metric_name,
                    "metricNamespace": metric_namespace,
                    "metricValue": "1",
                    "dimensions": {"event": "$.event", "workflow": "$.workflow"},
                },
            ],
        )
    os.environ["CIRRUS_WORKFLOW_METRIC_NAMESPACE"] = metric_namespace

    sleep(10)
    metric_logger = WorkflowMetricLogger(log_group_name=log_group_name, batch_size=1)
    assert metric_logger.enabled()
    event = make_event()
    mark = datetime.now(tz=UTC)
    metric_logger.add(event)
    metric_logger.add(event)
    sleep(20)  # wait for metrics to be available

    reader = WorkflowMetricReader(metric_namespace=metric_namespace)
    assert reader.enabled()
    stats = reader.aggregated_for_specified_workflows(
        workflows=["copier"],
        start_time=mark - timedelta(seconds=30),
        end_time=mark + timedelta(seconds=30),
        period=1,
    )
    stats_str = pformat(stats)
    assert type(stats) is dict
    assert len(stats) == 1, f"stats = {stats_str}"
    assert next(iter(stats.values()))["SUCCEEDED"]["SampleCount"] == 2.0, (
        f"stats = {stats_str}"
    )
