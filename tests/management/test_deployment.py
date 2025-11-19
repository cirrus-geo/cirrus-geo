"""Tests for Step Functions-related Deployment methods"""

import time

import pytest

from botocore.exceptions import ClientError

from cirrus.management.deployment import Deployment, NoExecutionsError
from tests.management.conftest import mock_parameters

# Test fixtures


@pytest.fixture
def deployment(queue, payloads, data, statedb, workflow, iam_role):
    """Create a Deployment instance with moto-mocked AWS services"""
    environment = mock_parameters(
        queue,
        payloads,
        data,
        statedb,
        workflow,
        "test-deployment",
        iam_role,
    )
    return Deployment(
        name="test-deployment",
        environment=environment,
    )


# Tests for get_execution_arn


def test_get_execution_arn_with_arn(deployment):
    """Test getting execution ARN when ARN is provided directly"""
    test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-123"
    result = deployment.get_execution_arn(arn=test_arn)
    assert result == test_arn


def test_get_execution_arn_with_payload_id(deployment, statedb):
    """Test getting execution ARN from payload_id"""
    test_payload_id = "test-col/workflow-test-wf/item1/item2"
    test_arn = "arn:aws:states:us-east-1:123456789:execution:my-sm:exec-456"

    statedb.claim_processing(test_payload_id, execution_arn=test_arn)
    statedb.set_processing(test_payload_id)

    result = deployment.get_execution_arn(payload_id=test_payload_id)
    assert result == test_arn


def test_get_execution_arn_with_no_executions(deployment, dynamo):
    """Test error when payload_id has executions list but it's empty"""
    test_payload_id = "test-col/workflow-test-wf/item-no-exec/item2"

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


# Tests for get_workflow_definition


def test_get_workflow_definition_success(deployment, workflow):
    """Test that get_workflow_definition constructs ARN correctly and returns workflow details"""
    # The method concatenates CIRRUS_BASE_WORKFLOW_ARN + workflow_name
    result = deployment.get_workflow_definition("test-workflow1")

    assert result["stateMachineArn"] == workflow["stateMachineArn"]
    assert result["name"] == "test-workflow1"


def test_get_workflow_definition_not_found(deployment):
    """Test that get_workflow_definition raises error for nonexistent workflow"""
    with pytest.raises(ClientError) as exc_info:
        deployment.get_workflow_definition("nonexistent-workflow")

    assert exc_info.value.response["Error"]["Code"] == "StateMachineDoesNotExist"


# Tests for get_execution_events


def test_get_execution_events_returns_all_events(deployment, st_func_execution_arn):
    """Test that get_execution_events returns events in expected format"""
    result = deployment.get_execution_events(st_func_execution_arn)

    # The method returns {"events": [...]}
    assert "events" in result
    assert isinstance(result["events"], list)
    assert len(result["events"]) > 0


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


# Tests for get_lambda_logs and get_batch_logs (smoke tests for thin wrappers)


def test_get_lambda_logs(deployment, logs):
    """Test that Deployment.get_lambda_logs wrapper works correctly"""

    log_group = "/aws/lambda/test-function"
    request_id = "test-req-wrapper"

    # CloudWatch rejects events older than 14 days
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]wrapper",
    )
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName="2025/11/11/[$LATEST]wrapper",
        logEvents=[
            {"timestamp": now_ms, "message": f"START RequestId: {request_id}\n"},
            {"timestamp": now_ms + 1000, "message": f"END RequestId: {request_id}\n"},
        ],
    )

    # Test that wrapper correctly passes args to underlying function
    result = deployment.get_lambda_logs(log_group, request_id)

    assert "logs" in result
    assert len(result["logs"]) == 2


def test_get_batch_logs(deployment, logs):
    """Test that Deployment.get_batch_logs wrapper works correctly"""

    log_group = "/aws/batch/job"
    log_stream = "test-job-def/default/wrapper-task"

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
            {"timestamp": now_ms, "message": "Wrapper test\n"},
        ],
    )

    # Test that wrapper correctly passes args to underlying function
    result = deployment.get_batch_logs(log_stream)

    assert "logs" in result
    assert len(result["logs"]) == 1
