"""Tests for Step Functions-related Deployment methods"""

import json

from unittest.mock import Mock, patch

import boto3
import pytest

from cirrus.management.deployment import Deployment, NoExecutionsError


@pytest.fixture
def mock_deployment():
    """Create a mock Deployment instance for testing"""
    environment = {
        "CIRRUS_PAYLOAD_BUCKET": "test-bucket",
        "CIRRUS_BASE_WORKFLOW_ARN": "arn:aws:states:us-east-1:123456789:stateMachine:test",
        "CIRRUS_PROCESS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/test",
        "CIRRUS_STATE_DB": "test-state-db",
        "CIRRUS_EVENT_DB_AND_TABLE": "test-db|test-table",
        "CIRRUS_PREFIX": "test-prefix",
    }

    # Create deployment with mocked session
    with patch("cirrus.management.deployment.assume_role") as mock_assume:
        mock_session = Mock(spec=boto3.Session)
        mock_assume.return_value = mock_session

        return Deployment(
            name="test-deployment",
            environment=environment,
            session=mock_session,
        )


class TestGetExecutionArn:
    """Tests for get_execution_arn method"""

    def test_get_execution_arn_with_arn(self, mock_deployment):
        """Test getting execution ARN when ARN is provided directly"""
        # Arrange
        test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"

        # Act
        result = mock_deployment.get_execution_arn(arn=test_arn)

        # Assert
        assert result == test_arn

    def test_get_execution_arn_with_payload_id(self, mock_deployment):
        """Test getting execution ARN from payload_id"""
        # Arrange
        test_payload_id = "test-payload-123"
        test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-456"

        mock_deployment.get_payload_state = Mock(
            return_value={
                "executions": [
                    "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-old",
                    test_arn,  # Most recent execution
                ],
            },
        )

        # Act
        result = mock_deployment.get_execution_arn(payload_id=test_payload_id)

        # Assert
        assert result == test_arn
        mock_deployment.get_payload_state.assert_called_once_with(test_payload_id)

    def test_get_execution_arn_with_no_executions(self, mock_deployment):
        """Test error when payload_id has no executions"""
        # Arrange
        test_payload_id = "test-payload-no-execs"

        mock_deployment.get_payload_state = Mock(
            return_value={
                "executions": [],
            },
        )

        # Act & Assert
        with pytest.raises(NoExecutionsError):
            mock_deployment.get_execution_arn(payload_id=test_payload_id)

    def test_get_execution_arn_with_neither(self, mock_deployment):
        """Test error when neither arn nor payload_id provided"""
        # Act & Assert
        with pytest.raises(
            ValueError,
            match="Either arn or payload_id must be provided",
        ):
            mock_deployment.get_execution_arn()

    def test_get_execution_arn_prefers_arn(self, mock_deployment):
        """Test that arn takes precedence when both are provided"""
        # Arrange
        test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"
        test_payload_id = "test-payload-456"

        # Act
        result = mock_deployment.get_execution_arn(
            arn=test_arn,
            payload_id=test_payload_id,
        )

        # Assert
        assert result == test_arn


class TestGetStateMachine:
    """Tests for get_state_machine method"""

    def test_get_state_machine_success(self, mock_deployment):
        """Test successful state machine retrieval"""
        # Arrange
        test_arn = "arn:aws:states:us-east-1:123456789:stateMachine:my-state-machine"
        expected_response = {
            "stateMachineArn": test_arn,
            "name": "my-state-machine",
            "status": "ACTIVE",
            "definition": json.dumps(
                {
                    "Comment": "Test state machine",
                    "StartAt": "FirstState",
                    "States": {
                        "FirstState": {
                            "Type": "Pass",
                            "End": True,
                        },
                    },
                },
            ),
            "roleArn": "arn:aws:iam::123456789:role/test-role",
            "type": "STANDARD",
            "creationDate": "2025-01-01T00:00:00.000Z",
        }

        mock_sfn_client = Mock()
        mock_sfn_client.describe_state_machine.return_value = expected_response

        with patch(
            "cirrus.management.deployment.get_client",
            return_value=mock_sfn_client,
        ):
            # Act
            result = mock_deployment.get_state_machine(test_arn)

        # Assert
        assert result == expected_response
        mock_sfn_client.describe_state_machine.assert_called_once_with(
            stateMachineArn=test_arn,
        )

    def test_get_state_machine_not_found(self, mock_deployment):
        """Test state machine not found error"""
        from botocore.exceptions import ClientError

        test_arn = "arn:aws:states:us-east-1:123456789:stateMachine:nonexistent"

        mock_sfn_client = Mock()
        mock_sfn_client.describe_state_machine.side_effect = ClientError(
            {
                "Error": {
                    "Code": "StateMachineDoesNotExist",
                    "Message": "State machine not found",
                },
            },
            "DescribeStateMachine",
        )

        with patch(
            "cirrus.management.deployment.get_client",
            return_value=mock_sfn_client,
        ):
            # Act & Assert
            with pytest.raises(ClientError) as exc_info:
                mock_deployment.get_state_machine(test_arn)

            assert (
                exc_info.value.response["Error"]["Code"] == "StateMachineDoesNotExist"
            )


class TestGetExecutionHistory:
    """Tests for get_execution_history method"""

    def test_get_execution_history_single_page(self, mock_deployment):
        """Test execution history retrieval with single page"""
        # Arrange
        test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"
        test_events = [
            {
                "id": 1,
                "type": "ExecutionStarted",
                "timestamp": "2025-01-01T00:00:00.000Z",
            },
            {
                "id": 2,
                "type": "TaskStateEntered",
                "timestamp": "2025-01-01T00:00:01.000Z",
            },
            {"id": 3, "type": "TaskScheduled", "timestamp": "2025-01-01T00:00:02.000Z"},
        ]

        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"events": test_events}]

        mock_sfn_client = Mock()
        mock_sfn_client.get_paginator.return_value = mock_paginator

        with patch(
            "cirrus.management.deployment.get_client",
            return_value=mock_sfn_client,
        ):
            # Act
            result = mock_deployment.get_execution_history(test_arn)

        # Assert
        assert result == {"events": test_events}
        mock_sfn_client.get_paginator.assert_called_once_with("get_execution_history")
        mock_paginator.paginate.assert_called_once_with(executionArn=test_arn)

    def test_get_execution_history_multiple_pages(self, mock_deployment):
        """Test execution history retrieval with pagination"""
        # Arrange
        test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"

        page1_events = [
            {
                "id": 1,
                "type": "ExecutionStarted",
                "timestamp": "2025-01-01T00:00:00.000Z",
            },
            {
                "id": 2,
                "type": "TaskStateEntered",
                "timestamp": "2025-01-01T00:00:01.000Z",
            },
        ]
        page2_events = [
            {"id": 3, "type": "TaskScheduled", "timestamp": "2025-01-01T00:00:02.000Z"},
            {"id": 4, "type": "TaskStarted", "timestamp": "2025-01-01T00:00:03.000Z"},
        ]
        page3_events = [
            {"id": 5, "type": "TaskSucceeded", "timestamp": "2025-01-01T00:00:04.000Z"},
            {
                "id": 6,
                "type": "ExecutionSucceeded",
                "timestamp": "2025-01-01T00:00:05.000Z",
            },
        ]

        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {"events": page1_events},
            {"events": page2_events},
            {"events": page3_events},
        ]

        mock_sfn_client = Mock()
        mock_sfn_client.get_paginator.return_value = mock_paginator

        with patch(
            "cirrus.management.deployment.get_client",
            return_value=mock_sfn_client,
        ):
            # Act
            result = mock_deployment.get_execution_history(test_arn)

        # Assert
        expected_events = page1_events + page2_events + page3_events
        assert result == {"events": expected_events}
        assert len(result["events"]) == 6
        assert result["events"][0]["id"] == 1
        assert result["events"][5]["id"] == 6

    def test_get_execution_history_empty(self, mock_deployment):
        """Test execution history retrieval with no events"""
        # Arrange
        test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"

        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"events": []}]

        mock_sfn_client = Mock()
        mock_sfn_client.get_paginator.return_value = mock_paginator

        with patch(
            "cirrus.management.deployment.get_client",
            return_value=mock_sfn_client,
        ):
            # Act
            result = mock_deployment.get_execution_history(test_arn)

        # Assert
        assert result == {"events": []}

    def test_get_execution_history_not_found(self, mock_deployment):
        """Test execution not found error"""
        from botocore.exceptions import ClientError

        test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:nonexistent"

        mock_paginator = Mock()
        mock_paginator.paginate.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ExecutionDoesNotExist",
                    "Message": "Execution not found",
                },
            },
            "GetExecutionHistory",
        )

        mock_sfn_client = Mock()
        mock_sfn_client.get_paginator.return_value = mock_paginator

        with patch(
            "cirrus.management.deployment.get_client",
            return_value=mock_sfn_client,
        ):
            # Act & Assert
            with pytest.raises(ClientError) as exc_info:
                mock_deployment.get_execution_history(test_arn)

            assert exc_info.value.response["Error"]["Code"] == "ExecutionDoesNotExist"
