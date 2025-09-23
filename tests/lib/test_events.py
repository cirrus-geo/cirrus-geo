import contextlib
import os

from datetime import UTC, datetime, timedelta

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
def test_workflow_metric_reader_get_statistics(monkeypatch):
    """Test the WorkflowMetricReader by setting up metric filters and logging some
    events.  Then retrieve statistics and verify the results.  This test can only be run
    against real AWS because moto does not fully support CloudWatch Log Metric Filters.
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

    metric_logger = WorkflowMetricLogger(log_group_name=log_group_name, batch_size=1)
    assert metric_logger.enabled()
    event = make_event()
    metric_logger.add(event)
    metric_logger.add(event)

    now = datetime.now(tz=UTC)

    reader = WorkflowMetricReader(metric_namespace=metric_namespace)
    assert reader.enabled()
    start = now - timedelta(days=10)
    end = now
    stats = reader.aggregated_for_specified_workflows(["copier"], start, end)
    assert type(stats) is dict
    assert len(stats) > 0
