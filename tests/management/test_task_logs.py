"""Tests for AWS CloudWatch logs utilities"""

import copy
import json

from datetime import UTC, datetime

import boto3
import pytest

from cirrus.management.task_logs import (
    format_log_event,
    get_batch_logs,
    get_lambda_logs,
    parse_log_metadata,
)

# Multiple-use test fixture for parse_log_metadata tests


@pytest.fixture
def lambda_task_succeeded_execution_events():
    """Execution events with Lambda TaskSucceeded event"""
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


# Tests for parse_log_metadata


def test_parse_lambda_task_succeeded(lambda_task_succeeded_execution_events):
    """Test parsing log metadata from Lambda TaskSucceeded event"""
    result = parse_log_metadata(lambda_task_succeeded_execution_events)

    assert "logMetadata" in result["events"][1]["taskSucceededEventDetails"]
    metadata = result["events"][1]["taskSucceededEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/lambda/my-function"
    assert metadata["lambdaRequestId"] == "abc-123-def"
    assert metadata["StartTimeUnixMs"] == 1762358630000
    assert metadata["EndTimeUnixMs"] == 1762358632000


def test_parse_lambda_task_failed():
    """Test parsing log metadata from Lambda TaskFailed event"""
    execution_events = {
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

    result = parse_log_metadata(execution_events)

    assert "logMetadata" in result["events"][1]["taskFailedEventDetails"]
    metadata = result["events"][1]["taskFailedEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/lambda/my-function"
    assert metadata["lambdaRequestId"] == "xyz-789-ghi"
    assert metadata["StartTimeUnixMs"] == 1762358630000
    assert metadata["EndTimeUnixMs"] == 1762358632000


def test_parse_batch_task_succeeded():
    """Test parsing log metadata from Batch TaskSucceeded event"""
    execution_events = {
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

    result = parse_log_metadata(execution_events)

    assert "logMetadata" in result["events"][1]["taskSucceededEventDetails"]
    metadata = result["events"][1]["taskSucceededEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/batch/job"
    assert metadata["logStreamName"] == "my-job-def/default/task-12345"


def test_parse_batch_task_failed():
    """Test parsing log metadata from Batch TaskFailed event"""
    execution_events = {
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

    result = parse_log_metadata(execution_events)

    assert "logMetadata" in result["events"][1]["taskFailedEventDetails"]
    metadata = result["events"][1]["taskFailedEventDetails"]["logMetadata"]

    assert metadata["LogGroup"] == "/aws/batch/job"
    assert metadata["logStreamName"] == "my-job-def/default/task-67890"


def test_parse_multiple_tasks_with_retries():
    """Test parsing log metadata with multiple tasks including retries"""
    execution_events = {
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

    result = parse_log_metadata(execution_events)

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
    execution_events = {
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

    result = parse_log_metadata(execution_events)

    # Should return execution events unchanged (no tasks to process)
    assert len(result["events"]) == 2
    assert "logMetadata" not in result["events"][0]
    assert "logMetadata" not in result["events"][1]


def test_parse_does_not_modify_original(lambda_task_succeeded_execution_events):
    """Test that parsing doesn't modify the original execution events"""
    original_copy = copy.deepcopy(lambda_task_succeeded_execution_events)
    parse_log_metadata(lambda_task_succeeded_execution_events)
    assert lambda_task_succeeded_execution_events == original_copy


# Tests for get_lambda_logs


def test_get_lambda_logs_basic(logs):
    """Test successful retrieval of Lambda logs with filter pattern"""
    import time

    log_group = "/aws/lambda/test-function"
    request_id = "test-req-123"
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]abcdef123",
    )
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]abcdef123",
        logEvents=[
            {"timestamp": now_ms, "message": f"START RequestId: {request_id}\n"},
            {"timestamp": now_ms + 1000, "message": "Processing request\n"},
            {"timestamp": now_ms + 2000, "message": f"END RequestId: {request_id}\n"},
        ],
    )

    session = boto3.Session()
    result = get_lambda_logs(session, log_group, request_id)

    assert "logs" in result
    # Filter pattern matches lines that contain the request_id value, so only START and END
    assert len(result["logs"]) == 2
    assert result["logs"][0]["timestamp"] == now_ms
    assert result["logs"][0]["message"] == f"START RequestId: {request_id}\n"
    assert result["logs"][1]["timestamp"] == now_ms + 2000
    assert result["logs"][1]["message"] == f"END RequestId: {request_id}\n"


def test_get_lambda_logs_with_time_range(logs):
    """Test Lambda logs with time range filtering"""
    import time

    log_group = "/aws/lambda/test-function-time"
    request_id = "test-req-456"
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]test456",
    )
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]test456",
        logEvents=[
            {"timestamp": now_ms, "message": f"START RequestId: {request_id}\n"},
            {
                "timestamp": now_ms + 5000,
                "message": f"MIDDLE RequestId: {request_id}\n",
            },
            {"timestamp": now_ms + 10000, "message": f"END RequestId: {request_id}\n"},
        ],
    )

    session = boto3.Session()

    # Query with time range that excludes the last event
    result = get_lambda_logs(
        session,
        log_group,
        request_id,
        start_time=now_ms,
        end_time=now_ms + 6000,
    )

    assert "logs" in result
    assert len(result["logs"]) == 2  # Should only get START and MIDDLE
    assert result["logs"][0]["message"] == f"START RequestId: {request_id}\n"
    assert result["logs"][1]["message"] == f"MIDDLE RequestId: {request_id}\n"


def test_get_lambda_logs_pagination(logs):
    """Test Lambda logs pagination with limit and nextToken"""
    import time

    log_group = "/aws/lambda/test-function-pagination"
    request_id = "test-req-789"
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]test789",
    )

    # Create multiple log events
    log_events = [
        {
            "timestamp": now_ms + i * 1000,
            "message": f"Log {i} RequestId: {request_id}\n",
        }
        for i in range(5)
    ]
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]test789",
        logEvents=log_events,
    )

    session = boto3.Session()

    # Get first page with limit
    result1 = get_lambda_logs(session, log_group, request_id, limit=2)

    assert "logs" in result1
    assert len(result1["logs"]) == 2
    assert result1["logs"][0]["message"] == f"Log 0 RequestId: {request_id}\n"

    # If nextToken is present, get next page
    if "nextToken" in result1:
        result2 = get_lambda_logs(
            session,
            log_group,
            request_id,
            limit=2,
            next_token=result1["nextToken"],
        )
        assert "logs" in result2
        # Should get different logs than first page
        assert len(result2["logs"]) <= 3  # Remaining logs


def test_get_lambda_logs_not_found(logs):
    """Test Lambda logs when log group not found"""
    from botocore.exceptions import ClientError

    session = boto3.Session()

    with pytest.raises(ClientError) as exc_info:
        get_lambda_logs(session, "/aws/lambda/nonexistent", "abc-123")

    assert exc_info.value.response["Error"]["Code"] == "ResourceNotFoundException"


# Tests for get_batch_logs


def test_get_batch_logs_basic(logs):
    """Test successful retrieval of Batch logs"""
    import time

    log_group = "/aws/batch/job"
    log_stream = "test-job-def/default/task-abc123"
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName=log_stream,
    )
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName=log_stream,
        logEvents=[
            {"timestamp": now_ms, "message": "Job starting\n"},
            {"timestamp": now_ms + 1000, "message": "Processing data\n"},
            {"timestamp": now_ms + 2000, "message": "Job completed\n"},
        ],
    )

    session = boto3.Session()
    result = get_batch_logs(session, log_stream)

    assert "logs" in result
    assert len(result["logs"]) == 3
    assert result["logs"][0]["timestamp"] == now_ms
    assert result["logs"][0]["message"] == "Job starting\n"
    assert result["logs"][1]["timestamp"] == now_ms + 1000
    assert result["logs"][1]["message"] == "Processing data\n"
    assert result["logs"][2]["timestamp"] == now_ms + 2000
    assert result["logs"][2]["message"] == "Job completed\n"


def test_get_batch_logs_with_custom_log_group(logs):
    """Test Batch logs with custom log group name"""
    import time

    log_group = "/aws/batch/custom-group"
    log_stream = "custom-job/default/task-xyz789"
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName=log_stream,
    )
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName=log_stream,
        logEvents=[
            {"timestamp": now_ms, "message": "Custom job log\n"},
            {"timestamp": now_ms + 1000, "message": "Custom job completed\n"},
        ],
    )

    session = boto3.Session()
    result = get_batch_logs(session, log_stream, log_group_name=log_group)

    assert "logs" in result
    assert len(result["logs"]) == 2
    assert result["logs"][0]["message"] == "Custom job log\n"
    assert result["logs"][1]["message"] == "Custom job completed\n"


def test_get_batch_logs_pagination(logs):
    """Test Batch logs pagination with limit and nextToken"""
    import time

    log_group = "/aws/batch/job"
    log_stream = "pagination-job/default/task-page123"
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName=log_stream,
    )

    # Create multiple log events
    log_events = [
        {"timestamp": now_ms + i * 1000, "message": f"Batch log line {i}\n"}
        for i in range(5)
    ]
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName=log_stream,
        logEvents=log_events,
    )

    session = boto3.Session()

    # Get first page with limit
    result1 = get_batch_logs(session, log_stream, limit=2)

    assert "logs" in result1
    assert len(result1["logs"]) == 2
    assert result1["logs"][0]["message"] == "Batch log line 0\n"
    assert result1["logs"][1]["message"] == "Batch log line 1\n"

    # If nextToken is present, get next page
    if "nextToken" in result1:
        result2 = get_batch_logs(
            session,
            log_stream,
            limit=2,
            next_token=result1["nextToken"],
        )
        assert "logs" in result2
        # Should get different logs than first page
        if len(result2["logs"]) > 0:
            assert result2["logs"][0]["message"] == "Batch log line 2\n"


def test_get_batch_logs_empty_stream(logs):
    """Test Batch logs with empty log stream"""
    log_group = "/aws/batch/job"
    log_stream = "empty-job/default/task-empty"

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName=log_stream,
    )

    session = boto3.Session()
    result = get_batch_logs(session, log_stream)

    assert "logs" in result
    assert len(result["logs"]) == 0
    assert "nextToken" not in result


def test_get_batch_logs_not_found(logs):
    """Test Batch logs when log stream not found"""
    from botocore.exceptions import ClientError

    session = boto3.Session()

    with pytest.raises(ClientError) as exc_info:
        get_batch_logs(
            session,
            "nonexistent-stream",
        )

    assert exc_info.value.response["Error"]["Code"] == "ResourceNotFoundException"


# Tests for format_log_event


def test_format_log_event_basic():
    """Test basic log event formatting"""
    log_event = {
        "timestamp": 1699372800500,  # 2023-11-07 16:00:00.500 UTC
        "message": "This is a test log message",
    }

    result = format_log_event(log_event)

    assert result == "[2023-11-07 16:00:00.500000+00:00] This is a test log message"


def test_format_log_event_with_trailing_whitespace():
    """Test log event formatting strips all trailing whitespace"""
    log_event = {
        "timestamp": 1699372800000,  # 2023-11-07 16:00:00 UTC
        "message": "Log message with whitespace   \n\t",
    }

    result = format_log_event(log_event)

    assert result == "[2023-11-07 16:00:00+00:00] Log message with whitespace"
