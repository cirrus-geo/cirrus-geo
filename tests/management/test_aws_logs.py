"""Tests for AWS CloudWatch logs utilities"""

import json

from datetime import UTC, datetime

from cirrus.management.aws_logs import parse_log_metadata


class TestParseLogMetadata:
    """Tests for parse_log_metadata function"""

    def test_parse_lambda_task_succeeded(self):
        """Test parsing log metadata from Lambda TaskSucceeded event"""
        # Arrange - minimal execution history with Lambda task
        execution_history = {
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
                                "Payload": {"result": "success"},
                                "SdkResponseMetadata": {
                                    "RequestId": "abc-123-def-456",
                                },
                            },
                        ),
                    },
                },
            ],
        }

        # Act
        result = parse_log_metadata(execution_history)

        # Assert
        task_succeeded = result["events"][1]
        assert "logMetadata" in task_succeeded["taskSucceededEventDetails"]

        metadata = task_succeeded["taskSucceededEventDetails"]["logMetadata"]
        assert metadata["LogGroup"] == "/aws/lambda/my-function"
        assert metadata["lambdaRequestId"] == "abc-123-def-456"
        assert metadata["StartTimeUnixMs"] == 1762358630000  # 2025-11-05 16:03:50 UTC
        assert metadata["EndTimeUnixMs"] == 1762358632000  # 2025-11-05 16:03:52 UTC

    def test_parse_lambda_task_failed(self):
        """Test parsing log metadata from Lambda TaskFailed event"""
        # Arrange
        execution_history = {
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
                        "output": json.dumps(
                            {
                                "Error": "RuntimeError",
                                "SdkResponseMetadata": {
                                    "RequestId": "xyz-789-abc-012",
                                },
                            },
                        ),
                    },
                },
            ],
        }

        # Act
        result = parse_log_metadata(execution_history)

        # Assert
        task_failed = result["events"][1]
        assert "logMetadata" in task_failed["taskFailedEventDetails"]

        metadata = task_failed["taskFailedEventDetails"]["logMetadata"]
        assert metadata["LogGroup"] == "/aws/lambda/my-function"
        assert metadata["lambdaRequestId"] == "xyz-789-abc-012"

    def test_parse_batch_task_succeeded(self):
        """Test parsing log metadata from Batch TaskSucceeded event"""
        # Arrange
        execution_history = {
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
                                "JobName": "my-batch-job",
                            },
                        ),
                    },
                },
                {
                    "id": 2,
                    "type": "TaskSucceeded",
                    "previousEventId": 1,
                    "timestamp": datetime(2025, 11, 5, 16, 5, 0, tzinfo=UTC),
                    "taskSucceededEventDetails": {
                        "resourceType": "batch",
                        "resource": "submitJob",
                        "output": json.dumps(
                            {
                                "Container": {
                                    "LogStreamName": "my-job-def/default/task-12345",
                                },
                            },
                        ),
                    },
                },
            ],
        }

        # Act
        result = parse_log_metadata(execution_history)

        # Assert
        task_succeeded = result["events"][1]
        assert "logMetadata" in task_succeeded["taskSucceededEventDetails"]

        metadata = task_succeeded["taskSucceededEventDetails"]["logMetadata"]
        assert metadata["LogGroup"] == "/aws/batch/job"
        assert metadata["logStreamName"] == "my-job-def/default/task-12345"

    def test_parse_batch_task_failed(self):
        """Test parsing log metadata from Batch TaskFailed event"""
        # Arrange
        execution_history = {
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
                                "JobName": "my-batch-job",
                            },
                        ),
                    },
                },
                {
                    "id": 2,
                    "type": "TaskFailed",
                    "previousEventId": 1,
                    "timestamp": datetime(2025, 11, 5, 16, 5, 0, tzinfo=UTC),
                    "taskFailedEventDetails": {
                        "resourceType": "batch",
                        "resource": "submitJob",
                        "output": json.dumps(
                            {
                                "Container": {
                                    "LogStreamName": "my-job-def/default/task-failed-67890",
                                },
                            },
                        ),
                    },
                },
            ],
        }

        # Act
        result = parse_log_metadata(execution_history)

        # Assert
        task_failed = result["events"][1]
        assert "logMetadata" in task_failed["taskFailedEventDetails"]

        metadata = task_failed["taskFailedEventDetails"]["logMetadata"]
        assert metadata["LogGroup"] == "/aws/batch/job"
        assert metadata["logStreamName"] == "my-job-def/default/task-failed-67890"

    def test_multiple_tasks_with_retries(self):
        """Test that each task attempt gets its own log metadata"""
        # Arrange - execution with Lambda task that retries
        execution_history = {
            "events": [
                # First attempt
                {
                    "id": 1,
                    "type": "TaskScheduled",
                    "previousEventId": 0,
                    "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                    "taskScheduledEventDetails": {
                        "resourceType": "lambda",
                        "parameters": json.dumps(
                            {
                                "FunctionName": "arn:aws:lambda:us-east-1:123:function:my-func",
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
                        "output": json.dumps(
                            {
                                "SdkResponseMetadata": {
                                    "RequestId": "attempt-1-request-id",
                                },
                            },
                        ),
                    },
                },
                # Second attempt (retry)
                {
                    "id": 3,
                    "type": "TaskScheduled",
                    "previousEventId": 2,
                    "timestamp": datetime(2025, 11, 5, 16, 4, 0, tzinfo=UTC),
                    "taskScheduledEventDetails": {
                        "resourceType": "lambda",
                        "parameters": json.dumps(
                            {
                                "FunctionName": "arn:aws:lambda:us-east-1:123:function:my-func",
                            },
                        ),
                    },
                },
                {
                    "id": 4,
                    "type": "TaskSucceeded",
                    "previousEventId": 3,
                    "timestamp": datetime(2025, 11, 5, 16, 4, 2, tzinfo=UTC),
                    "taskSucceededEventDetails": {
                        "resourceType": "lambda",
                        "output": json.dumps(
                            {
                                "SdkResponseMetadata": {
                                    "RequestId": "attempt-2-request-id",
                                },
                            },
                        ),
                    },
                },
            ],
        }

        # Act
        result = parse_log_metadata(execution_history)

        # Assert - both attempts should have metadata
        first_attempt = result["events"][1]
        assert "logMetadata" in first_attempt["taskFailedEventDetails"]
        assert (
            first_attempt["taskFailedEventDetails"]["logMetadata"]["lambdaRequestId"]
            == "attempt-1-request-id"
        )

        second_attempt = result["events"][3]
        assert "logMetadata" in second_attempt["taskSucceededEventDetails"]
        assert (
            second_attempt["taskSucceededEventDetails"]["logMetadata"][
                "lambdaRequestId"
            ]
            == "attempt-2-request-id"
        )

    def test_skips_non_lambda_batch_tasks(self):
        """Test that non-Lambda/Batch tasks are skipped"""
        # Arrange
        execution_history = {
            "events": [
                {
                    "id": 1,
                    "type": "TaskScheduled",
                    "previousEventId": 0,
                    "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                    "taskScheduledEventDetails": {
                        "resourceType": "dynamodb",  # Not lambda or batch
                        "parameters": "{}",
                    },
                },
                {
                    "id": 2,
                    "type": "TaskSucceeded",
                    "previousEventId": 1,
                    "timestamp": datetime(2025, 11, 5, 16, 3, 52, tzinfo=UTC),
                    "taskSucceededEventDetails": {
                        "resourceType": "dynamodb",
                        "output": "{}",
                    },
                },
            ],
        }

        # Act
        result = parse_log_metadata(execution_history)

        # Assert - no metadata should be added
        task_succeeded = result["events"][1]
        assert "logMetadata" not in task_succeeded["taskSucceededEventDetails"]

    def test_does_not_modify_original(self):
        """Test that parse_log_metadata does not modify the input history"""
        # Arrange
        original_history = {
            "events": [
                {
                    "id": 1,
                    "type": "TaskScheduled",
                    "previousEventId": 0,
                    "timestamp": datetime(2025, 11, 5, 16, 3, 50, tzinfo=UTC),
                    "taskScheduledEventDetails": {
                        "resourceType": "lambda",
                        "parameters": json.dumps(
                            {
                                "FunctionName": "arn:aws:lambda:us-east-1:123:function:my-func",
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
                        "output": json.dumps(
                            {
                                "SdkResponseMetadata": {"RequestId": "test-id"},
                            },
                        ),
                    },
                },
            ],
        }

        # Act
        result = parse_log_metadata(original_history)

        # Assert - original should not have logMetadata
        assert (
            "logMetadata"
            not in original_history["events"][1]["taskSucceededEventDetails"]
        )
        # Result should have logMetadata
        assert "logMetadata" in result["events"][1]["taskSucceededEventDetails"]
