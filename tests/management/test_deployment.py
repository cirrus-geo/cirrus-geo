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


# Tests for get_workflow_summary


def test_get_workflow_summary(deployment, create_records, statedb):
    """Test getting workflow summary with default options"""
    summary = deployment.get_workflow_summary("sar-test-panda", "test")

    assert summary["collections"] == "sar-test-panda"
    assert summary["workflow"] == "test"
    assert "counts" in summary

    expected_states = [
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "INVALID",
        "ABORTED",
        "CLAIMED",
    ]
    for state in expected_states:
        assert state in summary["counts"]
        if state in ["COMPLETED", "FAILED"]:
            assert summary["counts"][state] == 2
        else:
            assert summary["counts"][state] == 0


def test_get_workflow_summary_with_since(deployment, create_records, statedb):
    """Test workflow summary with since filter"""
    from datetime import timedelta

    summary = deployment.get_workflow_summary(
        "sar-test-panda",
        "test",
        since=timedelta(days=1),
    )

    assert summary["collections"] == "sar-test-panda"
    assert summary["workflow"] == "test"

    # With 1 day filter, we should get different counts
    # Based on fixture: completed items are recent, one failed is old
    assert summary["counts"]["COMPLETED"] == 2
    assert summary["counts"]["FAILED"] == 1


def test_get_workflow_summary_with_limit(deployment, create_records, statedb):
    """Test workflow summary with limit option"""
    summary = deployment.get_workflow_summary(
        "sar-test-panda",
        "test",
        limit=1,
    )

    assert summary["collections"] == "sar-test-panda"
    assert summary["workflow"] == "test"

    # With limit=1, counts should be 0, 1, or "1+"
    for state in summary["counts"]:
        count = summary["counts"][state]
        assert count == 0 or count == 1 or count == "1+"


# Tests for get_workflow_stats


def test_get_workflow_stats(deployment):
    """Test getting workflow stats structure"""
    # We can't query timestream db data with moto, so just check the output structure
    stats = deployment.get_workflow_stats()

    # Verify the expected output structure
    assert "state_transitions" in stats
    assert "daily" in stats["state_transitions"]
    assert "hourly" in stats["state_transitions"]
    assert "hourly_rolling" in stats["state_transitions"]

    # Each should be a list
    assert isinstance(stats["state_transitions"]["daily"], list)
    assert isinstance(stats["state_transitions"]["hourly"], list)
    assert isinstance(stats["state_transitions"]["hourly_rolling"], list)


# Tests for get_workflow_items


def test_get_workflow_items(deployment, create_records, statedb):
    """Test getting workflow items with default options"""
    result = deployment.get_workflow_items("sar-test-panda", "test")

    assert "items" in result
    assert isinstance(result["items"], list)
    assert len(result["items"]) == 4


def test_get_workflow_items_with_state_filter(deployment, create_records, statedb):
    """Test workflow items with state filter"""
    result = deployment.get_workflow_items(
        "sar-test-panda",
        "test",
        state="COMPLETED",
    )

    assert len(result["items"]) == 2
    for item in result["items"]:
        assert item["state"] == "COMPLETED"


def test_get_workflow_items_with_since(deployment, create_records, statedb):
    """Test workflow items with since filter"""
    from datetime import timedelta

    result = deployment.get_workflow_items(
        "sar-test-panda",
        "test",
        since=timedelta(days=1),
    )

    assert len(result["items"]) == 3


def test_get_workflow_items_with_limit(deployment, create_records, statedb):
    """Test workflow items with limit option"""
    result = deployment.get_workflow_items(
        "sar-test-panda",
        "test",
        limit=2,
    )

    assert len(result["items"]) == 2


def test_get_workflow_items_with_pagination(deployment, create_records, statedb):
    """Test workflow items pagination with nextkey"""
    # Get first item (descending order by default) and use its payload_id as nextkey
    result1 = deployment.get_workflow_items(
        "sar-test-panda",
        "test",
        limit=1,
    )
    assert len(result1["items"]) == 1
    payload_id = result1["items"][0]["payload_id"]

    # Make sure we got the expected first item per the fixture
    assert payload_id == create_records["failed"][1]

    # Get the next page using nextkey
    result2 = deployment.get_workflow_items(
        "sar-test-panda",
        "test",
        nextkey=payload_id,
        limit=1,
    )

    assert len(result2["items"]) == 1
    # Check that the item returned in the page is expected per the fixture
    assert result2["items"][0]["payload_id"] == create_records["failed"][0]


def test_get_workflow_items_with_sort_ascending(deployment, create_records, statedb):
    """Test workflow items with ascending sort order"""
    # Default is descending
    result_desc = deployment.get_workflow_items("sar-test-panda", "test")
    assert result_desc["items"][0]["payload_id"] == create_records["failed"][1]

    # Test ascending
    result_asc = deployment.get_workflow_items(
        "sar-test-panda",
        "test",
        sort_ascending=True,
    )
    assert result_asc["items"][0]["payload_id"] == create_records["completed"][0]


def test_get_workflow_items_with_sort_index(deployment, create_records, statedb):
    """Test workflow items with different sort index"""
    # The default index is "updated"; test with "state_updated"
    result = deployment.get_workflow_items(
        "sar-test-panda",
        "test",
        sort_index="state_updated",
    )

    assert "items" in result
    assert isinstance(result["items"], list)


# Tests for get_workflow_item


def test_get_workflow_item(deployment, create_records, statedb):
    """Test getting individual workflow item"""
    result = deployment.get_workflow_item("sar-test-panda", "test", "completed-0")

    assert "item" in result
    assert result["item"]["collections"] == "sar-test-panda"
    assert result["item"]["workflow"] == "test"
    assert result["item"]["items"] == "completed-0"


# Tests for get_lambda_logs and get_batch_logs


def test_get_lambda_logs(deployment, logs):
    """Test getting Lambda logs via Deployment method"""
    import time

    log_group = "/aws/lambda/test-function"
    request_id = "test-req-456"

    # CloudWatch rejects events older than 14 days
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]test123",
    )
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]test123",
        logEvents=[
            {"timestamp": now_ms, "message": f"START RequestId: {request_id}\n"},
            {"timestamp": now_ms + 1000, "message": "Processing request\n"},
            {"timestamp": now_ms + 2000, "message": f"END RequestId: {request_id}\n"},
        ],
    )

    result = deployment.get_lambda_logs(log_group, request_id)

    assert "logs" in result
    # Filter pattern matches lines with "RequestId: {request_id}", so only START and END
    assert len(result["logs"]) == 2
    assert result["logs"][0]["message"] == f"START RequestId: {request_id}\n"
    assert result["logs"][1]["message"] == f"END RequestId: {request_id}\n"


def test_get_lambda_logs_with_time_range(deployment, logs):
    """Test getting Lambda logs with time range"""
    import time

    log_group = "/aws/lambda/test-function-2"
    request_id = "test-req-789"

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
            {"timestamp": now_ms + 5000, "message": f"END RequestId: {request_id}\n"},
        ],
    )

    result = deployment.get_lambda_logs(
        log_group,
        request_id,
        start_time=now_ms,
        end_time=now_ms + 10000,
    )

    assert "logs" in result
    assert len(result["logs"]) == 2


def test_get_batch_logs(deployment, logs):
    """Test getting Batch logs via Deployment method"""
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

    result = deployment.get_batch_logs(log_stream)

    assert "logs" in result
    assert len(result["logs"]) == 3
    assert result["logs"][0]["message"] == "Job starting\n"
    assert result["logs"][2]["message"] == "Job completed\n"


def test_get_batch_logs_with_custom_log_group(deployment, logs):
    """Test getting Batch logs with custom log group"""
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
        ],
    )

    result = deployment.get_batch_logs(log_stream, log_group_name=log_group)

    assert "logs" in result
    assert len(result["logs"]) == 1
    assert result["logs"][0]["message"] == "Custom job log\n"
