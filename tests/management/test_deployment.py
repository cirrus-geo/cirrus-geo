"""Tests for Step Functions-related Deployment methods"""

import json

import pytest

from botocore.exceptions import ClientError

from cirrus.management.deployment import Deployment, NoExecutionsError

# Test fixtures


@pytest.fixture
def deployment_environment(statedb):
    """Environment configuration for test deployment"""
    return {
        "CIRRUS_PAYLOAD_BUCKET": "test-bucket",
        "CIRRUS_BASE_WORKFLOW_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:test-",
        "CIRRUS_PROCESS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/test",
        "CIRRUS_STATE_DB": "cirrus-test-state",  # Match the statedb fixture table name
        "CIRRUS_EVENT_DB_AND_TABLE": "event-db-1|event-table-1",
        "CIRRUS_PREFIX": "test-prefix",
    }


@pytest.fixture
def deployment(deployment_environment, statedb):
    """Create a Deployment instance with moto-mocked AWS services"""
    return Deployment(
        name="test-deployment",
        environment=deployment_environment,
    )


@pytest.fixture
def state_machine_arn(stepfunctions, iam_role):
    """Create a test state machine and return its ARN"""
    defn = {
        "Comment": "Test state machine",
        "StartAt": "FirstState",
        "States": {
            "FirstState": {
                "Type": "Pass",
                "End": True,
            },
        },
    }
    response = stepfunctions.create_state_machine(
        name="my-state-machine",
        definition=json.dumps(defn),
        roleArn=iam_role,
    )
    return response["stateMachineArn"]


@pytest.fixture
def execution_arn(stepfunctions, state_machine_arn):
    """Create a test execution and return its ARN"""
    response = stepfunctions.start_execution(
        stateMachineArn=state_machine_arn,
        name="exec-123",
        input="{}",
    )
    return response["executionArn"]


# Tests for get_execution_arn


def test_get_execution_arn_with_arn(deployment):
    """Test getting execution ARN when ARN is provided directly"""
    test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"
    result = deployment.get_execution_arn(arn=test_arn)
    assert result == test_arn


def test_get_execution_arn_with_payload_id(deployment, statedb):
    """Test getting execution ARN from payload_id"""
    # Use proper payload_id format: collection/workflow-name/item1/item2
    test_payload_id = "test-col/workflow-test-wf/item1/item2"
    test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-456"

    # Create payload state with executions
    statedb.claim_processing(test_payload_id, execution_arn=test_arn)
    statedb.set_processing(test_payload_id)

    result = deployment.get_execution_arn(payload_id=test_payload_id)
    assert result == test_arn


def test_get_execution_arn_with_no_executions(deployment, dynamo):
    """Test error when payload_id has executions list but it's empty"""
    # Use proper payload_id format: collection/workflow-name/item1/item2
    test_payload_id = "test-col/workflow-test-wf/item-no-exec/item2"

    # Manually create a DynamoDB item with empty executions list
    # This shouldn't happen in practice, but we test the error handling
    dynamo.put_item(
        TableName="cirrus-test-state",
        Item={
            "collections_workflow": {"S": "test-col_test-wf"},
            "itemids": {"S": "item-no-exec/item2"},
            "state_updated": {"S": "PROCESSING"},
            "executions": {"L": []},  # Empty executions list
        },
    )

    with pytest.raises(NoExecutionsError):
        deployment.get_execution_arn(payload_id=test_payload_id)


def test_get_execution_arn_with_neither(deployment):
    """Test error when neither arn nor payload_id provided"""
    with pytest.raises(
        ValueError,
        match="Either arn or payload_id must be provided",
    ):
        deployment.get_execution_arn()


def test_get_execution_arn_prefers_arn(deployment):
    """Test that arn takes precedence when both are provided"""
    test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"
    test_payload_id = "test-payload-456"

    result = deployment.get_execution_arn(
        arn=test_arn,
        payload_id=test_payload_id,
    )

    assert result == test_arn


# Tests for get_state_machine


def test_get_workflow_defintion_success(deployment, stepfunctions, state_machine_arn):
    """Test successful workflow definition retrieval"""
    # The test should use the actual workflow name without the prefix
    # Since the ARN is 'arn:aws:states:us-east-1:123456789012:stateMachine:my-state-machine'
    # and the base ARN is 'arn:aws:states:us-east-1:123456789012:stateMachine:test-'
    # we need to find the workflow name that would produce this ARN

    # For this test to work, we need to create a state machine that matches the expected naming pattern
    # Let's create a new state machine with the prefix expected by get_workflow_definition
    test_defn = {
        "Comment": "Test workflow definition",
        "StartAt": "TestState",
        "States": {
            "TestState": {
                "Type": "Pass",
                "End": True,
            },
        },
    }

    # Get the IAM role from the existing state machine
    existing_sm = stepfunctions.describe_state_machine(
        stateMachineArn=state_machine_arn,
    )
    iam_role = existing_sm["roleArn"]

    # Create a state machine with the expected prefix naming
    test_sm = stepfunctions.create_state_machine(
        name="test-workflow1",  # This will create ARN ending with test-workflow1
        definition=json.dumps(test_defn),
        roleArn=iam_role,
    )

    # Now test get_workflow_definition with just the workflow name part
    result = deployment.get_workflow_definition("workflow1")

    assert result["stateMachineArn"] == test_sm["stateMachineArn"]
    assert result["name"] == "test-workflow1"
    assert result["status"] == "ACTIVE"
    assert "definition" in result
    assert "roleArn" in result
    assert result["type"] == "STANDARD"


def test_get_workflow_definition_not_found(deployment, stepfunctions):
    """Test workflow not found error"""
    # Use a workflow name that doesn't exist
    workflow_name = "nonexistent-workflow"

    with pytest.raises(ClientError) as exc_info:
        deployment.get_workflow_definition(workflow_name)

    # Moto returns StateMachineDoesNotExist for valid ARN format
    assert exc_info.value.response["Error"]["Code"] == "StateMachineDoesNotExist"


# Tests for get_execution_events


def test_get_execution_events_single_page(deployment, stepfunctions, execution_arn):
    """Test execution events retrieval with single page"""
    result = deployment.get_execution_events(execution_arn)

    assert "events" in result
    assert isinstance(result["events"], list)
    assert len(result["events"]) > 0
    # Verify basic event structure
    assert "id" in result["events"][0]
    assert "type" in result["events"][0]
    assert "timestamp" in result["events"][0]


def test_get_execution_events_multiple_pages(
    deployment,
    stepfunctions,
    state_machine_arn,
    iam_role,
):
    """Test execution events retrieval with pagination"""
    # Create an execution with multiple events by using a more complex state machine
    complex_defn = {
        "StartAt": "State1",
        "States": {
            "State1": {"Type": "Pass", "Next": "State2"},
            "State2": {"Type": "Pass", "Next": "State3"},
            "State3": {"Type": "Pass", "Next": "State4"},
            "State4": {"Type": "Pass", "End": True},
        },
    }

    # Create a new state machine with complex definition - use iam_role fixture
    complex_sm = stepfunctions.create_state_machine(
        name="complex-state-machine",
        definition=json.dumps(complex_defn),
        roleArn=iam_role,
    )

    # Start execution
    execution = stepfunctions.start_execution(
        stateMachineArn=complex_sm["stateMachineArn"],
        name="complex-exec",
        input="{}",
    )

    result = deployment.get_execution_events(execution["executionArn"])

    assert "events" in result
    assert isinstance(result["events"], list)
    assert len(result["events"]) > 0


def test_get_execution_events_empty(deployment, stepfunctions, execution_arn):
    """Test execution events always has at least ExecutionStarted event"""
    result = deployment.get_execution_events(execution_arn)

    assert "events" in result
    assert len(result["events"]) >= 1
    # First event should be ExecutionStarted
    assert result["events"][0]["type"] == "ExecutionStarted"


def test_get_execution_events_not_found(deployment, stepfunctions):
    """Test execution not found error"""
    # Use valid ARN format with moto account ID
    test_arn = "arn:aws:states:us-east-1:123456789012:execution:my-sm:nonexistent"

    with pytest.raises(ClientError) as exc_info:
        deployment.get_execution_events(test_arn)

    assert exc_info.value.response["Error"]["Code"] == "ExecutionDoesNotExist"
