import json
import os
import time

import pytest

from click.testing import Result

from cirrus.management.deployment import (
    Deployment,
)
from tests.management.conftest import mock_parameters

MOCK_DEPLOYMENT_NAME = "lion"
STACK_NAME = "cirrus-test"
MOCK_CIRRUS_PREFIX = "ts-lion-dev-cirrus"


@pytest.fixture
def manage(invoke):
    def _manage(cmd, **kwargs):
        return invoke("manage " + cmd, **kwargs)

    return _manage


@pytest.fixture
def deployment(manage, queue, payloads, data, statedb, workflow, sts, iam_role):
    def _manage(deployment, cmd):
        return manage(f"{deployment.name} {cmd}")

    Deployment.__call__ = _manage

    return Deployment(
        MOCK_DEPLOYMENT_NAME,
        mock_parameters(
            queue,
            payloads,
            data,
            statedb,
            workflow,
            MOCK_DEPLOYMENT_NAME,
            iam_role,
        ),
    )


def test_manage(manage):
    result = manage("")
    assert result.exit_code == 2
    assert result.output.startswith("Usage: cirrus manage ")


def test_get_execution_by_arn(deployment, st_func_execution_arn, sts):
    result = deployment(
        f"get-execution --arn {st_func_execution_arn}",
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout.strip())["executionArn"] == st_func_execution_arn


def test_manage_get_execution_by_payload_id(
    deployment,
    create_records,
    put_parameters,
    st_func_execution_arn,
) -> None:
    result = deployment(
        "get-execution --payload-id sar-test-panda/workflow-test/completed-0",
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout.strip())["executionArn"] == st_func_execution_arn


@pytest.fixture
def _management_env(_environment, payloads, workflow):
    state_machine_arn = workflow["stateMachineArn"]
    os.environ["CIRRUS_BASE_WORKFLOW_ARN"] = state_machine_arn[: -len("test-workflow1")]
    os.environ["CIRRUS_PAYLOAD_BUCKET"] = payloads


@pytest.mark.usefixtures("_management_env")
def test_manage_get_execution_arn_by_payload_id_twice(
    deployment,
    basic_payload_managers_factory,
    wfem,
) -> None:
    """Causes two workflow executions of the same payload, and confirms that the second
    call to get_execution_arn with payload_id gets a different executionArn value from
    the first execution. This confirms that we are getting the most recent execution ARN
    from dynamodb, as new ones are simply appended.
    """
    basic_payload_managers1 = basic_payload_managers_factory()
    basic_payload_managers1.process(wfem)
    pid = basic_payload_managers1[0].payload["id"]
    exec_arn1 = deployment.get_execution_arn(payload_id=pid)

    # alter state to allow a new workflow execution of the same payload
    wfem.aborted(pid, execution_arn=exec_arn1)

    # Create a new PayloadManagers object so it fetches fresh state
    basic_payload_managers2 = basic_payload_managers_factory()
    basic_payload_managers2.process(wfem)
    exec_arn2 = deployment.get_execution_arn(payload_id=pid)
    assert exec_arn1 != exec_arn2


# using non-stac payloads for simpler testing
def test_get_payload(
    deployment,
    create_records,
):
    for payload_id in create_records["completed"]:
        result = deployment(f"get-payload {payload_id}")
        assert result.exit_code == 0
        assert json.loads(result.stdout.strip())["payload_id"] == payload_id


def test_get_state(deployment, create_records):
    for payload_id in create_records["completed"]:
        result = deployment(f"get-state {payload_id}")
        assert result.exit_code == 0
        output = json.loads(result.stdout.strip())
        actual_payload_id = (
            output["collections_workflow"].split("_")[0]
            + "/workflow-"
            + output["collections_workflow"].split("_")[1]
            + "/"
            + output["itemids"]
        )
        assert actual_payload_id == payload_id


def test_manage_show_unknown_deployment(manage, put_parameters):
    unknown = "unknown-deployment"
    result = manage(f"{unknown} show")
    assert result.exit_code == 1
    assert result.stderr.strip() == f"Deployment not found: '{unknown}'"


def test_list_deployments(invoke, put_parameters):
    result = invoke("list-deployments")
    assert result.exit_code == 0
    assert result.stdout.strip().splitlines() == ["lion", "squirrel-dev"]


def test_list_lambdas(deployment, make_lambdas, put_parameters, iam_role):
    result = deployment("list-lambdas")
    assert result.exit_code == 0
    assert result.stdout.strip() == json.dumps(
        {
            "Functions": [
                "process",
            ],
        },
        indent=4,
    )


def test_process(deployment, manage, make_lambdas, put_parameters):
    result = manage("lion process", input='{"a": "payload to test process command"}')
    assert result.exit_code == 0

    # The process command returns SQS metadata when the payload is successfully enqueued
    output = json.loads(result.stdout.strip())
    assert "MessageId" in output
    assert "MD5OfMessageBody" in output
    assert output["ResponseMetadata"]["HTTPStatusCode"] == 200


def test_manage_show_deployment(deployment, put_parameters):
    result = deployment("show")
    assert result.exit_code == 0
    assert result.stdout.strip() == json.dumps(deployment.environment, indent=4)


@pytest.mark.parametrize(
    ("command", "expect_exit_zero"),
    [
        ("true", True),
        ("false", False),
    ],
)
def test_call_cli_return_values(deployment, command, expect_exit_zero, put_parameters):
    result = deployment(f"call {command}")
    assert result.exit_code == 0 if expect_exit_zero else result.exit_code != 0


def assert_get_payloads(
    result: Result,
    create_records: dict[str, list[str]],
    state: str,
    limit: int | None,
):
    assert result.exit_code == 0
    output = result.stdout.strip().split("\n")

    expected_record_count = len(create_records[state])
    if limit:
        expected_record_count = limit
    assert expected_record_count == len(output)

    for obj in output:
        payload = json.loads(obj)
        assert payload["payload_id"] in create_records[state]
        assert payload["process"][0]["replace"]


@pytest.mark.parametrize(
    ("state", "parameter", "limit"),
    [
        pytest.param(
            "completed",
            "--state 'COMPLETED'",
            None,
            id="state=COMPLETED flag",
        ),
        pytest.param("failed", "--state 'FAILED'", None, id="state=FAILED flag"),
        pytest.param(
            "completed",
            "--since '10d' --state 'COMPLETED'",
            None,
            id="since flag",
        ),
        pytest.param(
            "failed",
            "--state 'FAILED' --error-prefix 'failed-error-message'",
            None,
            id="error prefix flag",
        ),
        pytest.param("completed", "--state 'COMPLETED' --limit 1", 1, id="limit flag"),
    ],
)
def test_get_payloads(deployment, create_records, statedb, state, parameter, limit):
    result = deployment(
        f"get-payloads --collections-workflow 'sar-test-panda_test' {parameter} --rerun",
    )
    assert_get_payloads(result, create_records, state, limit)


def test_get_workflow_definition(deployment, workflow, put_parameters):
    state_machine_arn = workflow["stateMachineArn"]
    result = deployment("get-workflow-definition test-workflow1")

    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())
    assert output["stateMachineArn"] == state_machine_arn
    assert output["name"] == "test-workflow1"
    assert "definition" in output


def test_get_execution_events(deployment, st_func_execution_arn, put_parameters):
    result = deployment(f"get-execution-events --arn {st_func_execution_arn}")

    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())
    assert len(output["events"]) == 4
    assert output["events"][0]["type"] == "ExecutionStarted"


def test_get_execution_events_with_log_metadata(
    deployment,
    st_func_execution_arn,
    put_parameters,
):
    result = deployment(
        f"get-execution-events --arn {st_func_execution_arn} --with-log-metadata",
    )

    # our test state machine has no lambda or batch steps, so there is no log metadata
    # to inject; this just tests that the flag works without error.
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())
    assert len(output["events"]) == 4


def test_get_lambda_logs(deployment, logs, put_parameters):
    log_group = "/aws/lambda/test-function"
    request_id = "test-req-123"

    # CloudWatch rejects events older than 14 days
    now_ms = int(time.time() * 1000)

    logs.create_log_group(logGroupName=log_group)
    logs.create_log_stream(
        logGroupName=log_group,
        logStreamName="2025/11/10/[$LATEST]abcdef",
    )
    logs.put_log_events(
        logGroupName=log_group,
        logStreamName="2025/11/10/[$LATEST]abcdef",
        logEvents=[
            {"timestamp": now_ms, "message": f"START RequestId: {request_id}\n"},
            {"timestamp": now_ms + 1000, "message": "Test log message\n"},
            {"timestamp": now_ms + 2000, "message": f"END RequestId: {request_id}\n"},
        ],
    )

    result = deployment(f"get-lambda-logs {log_group} {request_id}")

    assert result.exit_code == 0
    assert f"START RequestId: {request_id}" in result.stdout
    assert f"END RequestId: {request_id}" in result.stdout


def test_get_batch_logs(deployment, logs, put_parameters):
    log_group = "/aws/batch/job"
    log_stream = "my-job-def/default/task-12345"

    # CloudWatch rejects events older than 14 days
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
            {"timestamp": now_ms, "message": "Batch job started\n"},
            {"timestamp": now_ms + 1000, "message": "Processing data\n"},
            {"timestamp": now_ms + 2000, "message": "Batch job completed\n"},
        ],
    )

    result = deployment(f"get-batch-logs {log_stream}")

    assert result.exit_code == 0
    assert "Batch job started" in result.stdout
    assert "Processing data" in result.stdout
    assert "Batch job completed" in result.stdout
