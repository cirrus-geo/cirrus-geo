"""Tests for AWS CloudWatch logs utilities"""

import json

from datetime import UTC, datetime

import boto3
import pytest

from cirrus.management.task_logs import (
    get_batch_logs,
    get_lambda_logs,
    parse_log_metadata,
)

# Test fixtures for parse_log_metadata tests


@pytest.fixture
def lambda_task_succeeded_history():
    """Execution history with Lambda TaskSucceeded event"""
    return {
        "events": [
            {
                "id": 1,
                "type": "TaskScheduled",
                "previousEventId": 0,
                "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                "taskScheduledEventDetails": {
                    "resourceType": "lambda",
                    "resource": "invoke",
                    "parameters": json.dumps(
                        {
                            "FunctionName": "arn:aws:lambda:us-east-1:123456789:function:my-function",
                            "Payload": {},
                        },
                    ),
                },
            },
            {
                "id": 2,
                "type": "TaskSucceeded",
                "previousEventId": 1,
                "timestamp": datetime(2025, 11, 5, 16, 3, 52, tzinfo=UTC),
                "taskSucceededEventDetails": {
                    "resourceType": "lambda",
                    "resource": "invoke",
                    "output": json.dumps(
                        {
                            "StatusCode": 200,
                            "SdkResponseMetadata": {
                                "RequestId": "abc-123-def",
                            },
                        },
                    ),
                },
            },
        ],
    }


@pytest.fixture
def lambda_task_failed_history():
    """Execution history with Lambda TaskFailed event"""
    return {
        "events": [
            {
                "id": 1,
                "type": "TaskScheduled",
                "previousEventId": 0,
                "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                "taskScheduledEventDetails": {
                    "resourceType": "lambda",
                    "resource": "invoke",
                    "parameters": json.dumps(
                        {
                            "FunctionName": "arn:aws:lambda:us-east-1:123456789:function:my-function",
                            "Payload": {},
                        },
                    ),
                },
            },
            {
                "id": 2,
                "type": "TaskFailed",
                "previousEventId": 1,
                "timestamp": datetime(2025, 11, 5, 16, 3, 52, tzinfo=UTC),
                "taskFailedEventDetails": {
                    "resourceType": "lambda",
                    "resource": "invoke",
                    "error": "Exception",
                    "cause": json.dumps(
                        {
                            "errorMessage": "Forced error for testing purposes",
                            "errorType": "Exception",
                            "requestId": "xyz-789-ghi",
                            "stackTrace": [
                                '  File "/var/task/handler.py", line 10, in handler\n    raise Exception("error")\n',
                            ],
                        },
                    ),
                },
            },
        ],
    }


@pytest.fixture
def batch_task_succeeded_history():
    """Execution history with Batch TaskSucceeded event"""
    return {
        "events": [
            {
                "id": 1,
                "type": "TaskScheduled",
                "previousEventId": 0,
                "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                "taskScheduledEventDetails": {
                    "resourceType": "batch",
                    "resource": "submitJob",
                    "parameters": json.dumps(
                        {
                            "JobName": "my-job",
                            "JobQueue": "my-queue",
                        },
                    ),
                },
            },
            {
                "id": 2,
                "type": "TaskSucceeded",
                "previousEventId": 1,
                "timestamp": datetime(2025, 11, 5, 16, 5, 30, tzinfo=UTC),
                "taskSucceededEventDetails": {
                    "resourceType": "batch",
                    "resource": "submitJob",
                    "output": json.dumps(
                        {
                            "JobId": "job-123",
                            "Container": {
                                "LogStreamName": "my-job-def/default/task-12345",
                            },
                        },
                    ),
                },
            },
        ],
    }


@pytest.fixture
def batch_task_failed_history():
    """Execution history with Batch TaskFailed event"""
    return {
        "events": [
            {
                "id": 1,
                "type": "TaskScheduled",
                "previousEventId": 0,
                "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                "taskScheduledEventDetails": {
                    "resourceType": "batch",
                    "resource": "submitJob",
                    "parameters": json.dumps(
                        {
                            "JobName": "my-job",
                            "JobQueue": "my-queue",
                        },
                    ),
                },
            },
            {
                "id": 2,
                "type": "TaskFailed",
                "previousEventId": 1,
                "timestamp": datetime(2025, 11, 5, 16, 5, 30, tzinfo=UTC),
                "taskFailedEventDetails": {
                    "resourceType": "batch",
                    "resource": "submitJob",
                    "error": "States.TaskFailed",
                    "cause": json.dumps(
                        {
                            "JobId": "job-456",
                            "Status": "FAILED",
                            "Container": {
                                "ExitCode": 255,
                                "LogStreamName": "my-job-def/default/task-67890",
                            },
                        },
                    ),
                },
            },
        ],
    }


# Tests for parse_log_metadata


def test_parse_lambda_task_succeeded(lambda_task_succeeded_history):
    """Test parsing log metadata from Lambda TaskSucceeded event"""
    result = parse_log_metadata(lambda_task_succeeded_history)

    assert "logMetadata" in result["events"][1]["taskSucceededEventDetails"]
    metadata = result["events"][1]["taskSucceededEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/lambda/my-function"
    assert metadata["lambdaRequestId"] == "abc-123-def"
    assert metadata["StartTimeUnixMs"] == 1762358630000
    assert metadata["EndTimeUnixMs"] == 1762358632000


def test_parse_lambda_task_failed(lambda_task_failed_history):
    """Test parsing log metadata from Lambda TaskFailed event"""
    result = parse_log_metadata(lambda_task_failed_history)

    assert "logMetadata" in result["events"][1]["taskFailedEventDetails"]
    metadata = result["events"][1]["taskFailedEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/lambda/my-function"
    assert metadata["lambdaRequestId"] == "xyz-789-ghi"
    assert metadata["StartTimeUnixMs"] == 1762358630000
    assert metadata["EndTimeUnixMs"] == 1762358632000


def test_parse_batch_task_succeeded(batch_task_succeeded_history):
    """Test parsing log metadata from Batch TaskSucceeded event"""
    result = parse_log_metadata(batch_task_succeeded_history)

    assert "logMetadata" in result["events"][1]["taskSucceededEventDetails"]
    metadata = result["events"][1]["taskSucceededEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/batch/job"
    assert metadata["logStreamName"] == "my-job-def/default/task-12345"


def test_parse_batch_task_failed(batch_task_failed_history):
    """Test parsing log metadata from Batch TaskFailed event"""
    result = parse_log_metadata(batch_task_failed_history)

    assert "logMetadata" in result["events"][1]["taskFailedEventDetails"]
    metadata = result["events"][1]["taskFailedEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/batch/job"
    assert metadata["logStreamName"] == "my-job-def/default/task-67890"


def test_parse_multiple_tasks_with_retries():
    """Test parsing log metadata with multiple tasks including retries"""
    execution_history = {
        "events": [
            # First Lambda task (attempt 1 - failed)
            {
                "id": 1,
                "type": "TaskScheduled",
                "previousEventId": 0,
                "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                "taskScheduledEventDetails": {
                    "resourceType": "lambda",
                    "resource": "invoke",
                    "parameters": json.dumps(
                        {
                            "FunctionName": "arn:aws:lambda:us-east-1:123:function:func1",
                        },
                    ),
                },
            },
            {
                "id": 2,
                "type": "TaskFailed",
                "previousEventId": 1,
                "timestamp": datetime(2025, 11, 5, 16, 3, 51, tzinfo=UTC),
                "taskFailedEventDetails": {
                    "resourceType": "lambda",
                    "error": "Exception",
                    "cause": json.dumps(
                        {
                            "errorMessage": "Test error",
                            "errorType": "Exception",
                            "requestId": "req-1",
                            "stackTrace": [],
                        },
                    ),
                },
            },
            # First Lambda task (attempt 2 - succeeded)
            {
                "id": 3,
                "type": "TaskScheduled",
                "previousEventId": 2,
                "timestamp": datetime(2025, 11, 5, 16, 3, 52, tzinfo=UTC),
                "taskScheduledEventDetails": {
                    "resourceType": "lambda",
                    "resource": "invoke",
                    "parameters": json.dumps(
                        {
                            "FunctionName": "arn:aws:lambda:us-east-1:123:function:func1",
                        },
                    ),
                },
            },
            {
                "id": 4,
                "type": "TaskSucceeded",
                "previousEventId": 3,
                "timestamp": datetime(2025, 11, 5, 16, 3, 53, tzinfo=UTC),
                "taskSucceededEventDetails": {
                    "resourceType": "lambda",
                    "output": json.dumps(
                        {"SdkResponseMetadata": {"RequestId": "req-2"}},
                    ),
                },
            },
        ],
    }

    result = parse_log_metadata(execution_history)

    # Both attempts should have metadata
    assert "logMetadata" in result["events"][1]["taskFailedEventDetails"]
    assert "logMetadata" in result["events"][3]["taskSucceededEventDetails"]

    # Each should have different request IDs
    assert (
        result["events"][1]["taskFailedEventDetails"]["logMetadata"]["lambdaRequestId"]
        == "req-1"
    )
    assert (
        result["events"][3]["taskSucceededEventDetails"]["logMetadata"][
            "lambdaRequestId"
        ]
        == "req-2"
    )


def test_parse_skips_non_lambda_batch_tasks():
    """Test that non-Lambda/Batch tasks are skipped"""
    execution_history = {
        "events": [
            {
                "id": 1,
                "type": "PassStateEntered",
                "previousEventId": 0,
                "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
            },
            {
                "id": 2,
                "type": "PassStateExited",
                "previousEventId": 1,
                "timestamp": datetime(2025, 11, 5, 16, 3, 51, tzinfo=UTC),
            },
        ],
    }

    result = parse_log_metadata(execution_history)

    # Should return history unchanged (no tasks to process)
    assert len(result["events"]) == 2
    assert "logMetadata" not in result["events"][0]
    assert "logMetadata" not in result["events"][1]


def test_parse_does_not_modify_original(lambda_task_succeeded_history):
    """Test that parsing doesn't modify the original history"""
    parse_log_metadata(lambda_task_succeeded_history)

    # Original should be unchanged
    assert (
        "logMetadata"
        not in lambda_task_succeeded_history["events"][1]["taskSucceededEventDetails"]
    )


# Tests for get_lambda_logs


def test_get_lambda_logs_success(logs):
    """Test successful retrieval of Lambda logs - basic structure test"""
    session = boto3.Session()
    result = get_lambda_logs(
        session,
        "/aws/lambda/my-function",
        "abc-123",
        start_time=1730822630000,
        end_time=1730822632000,
    )

    # Verify the basic structure is correct
    assert "logs" in result
    assert isinstance(result["logs"], list)


def test_get_lambda_logs_without_time_range(logs):
    """Test Lambda logs retrieval without time filtering - basic structure test"""
    session = boto3.Session()
    result = get_lambda_logs(
        session,
        "/aws/lambda/my-function",
        "abc-123",
    )

    assert "logs" in result
    assert isinstance(result["logs"], list)


def test_get_lambda_logs_pagination(logs):
    """Test Lambda logs pagination with nextToken - basic structure test"""
    session = boto3.Session()
    result = get_lambda_logs(
        session,
        "/aws/lambda/my-function",
        "abc-123",
        limit=10,
    )

    assert "logs" in result
    assert isinstance(result["logs"], list)


def test_get_lambda_logs_not_found(logs):
    """Test Lambda logs when log group not found"""
    session = boto3.Session()
    result = get_lambda_logs(session, "/aws/lambda/nonexistent", "abc-123")

    assert result == {"logs": []}


# Tests for get_batch_logs


def test_get_batch_logs_success(logs):
    """Test successful retrieval of Batch logs - basic structure test"""
    session = boto3.Session()
    result = get_batch_logs(
        session,
        "my-job-def/default/task-12345",
    )

    assert "logs" in result
    assert isinstance(result["logs"], list)


def test_get_batch_logs_pagination(logs):
    """Test Batch logs pagination with nextToken - basic structure test"""
    session = boto3.Session()
    result = get_batch_logs(
        session,
        "my-job-def/default/task-12345",
        limit=10,
    )

    assert "logs" in result
    assert isinstance(result["logs"], list)


def test_get_batch_logs_not_found(logs):
    """Test Batch logs when log stream not found"""
    session = boto3.Session()
    result = get_batch_logs(
        session,
        "nonexistent-stream",
    )

    assert result == {"logs": []}
