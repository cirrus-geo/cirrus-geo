import json
import os

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
def test_manage_get_execution_by_payload_id_twice(
    deployment,
    basic_payload_managers_factory,
    wfem,
) -> None:
    """Causes two workflow executions of the same payload, and confirms that the second
    call to get_execution_by_payload_id gets a different executionArn value from the
    first execution. This confirms that we are getting the most recent execution ARN
    from dynamodb, as new ones are simply appended.
    """
    basic_payload_managers1 = basic_payload_managers_factory()
    basic_payload_managers1.process(wfem)
    pid = basic_payload_managers1[0].payload["id"]
    sfn_exe1 = deployment.get_execution_by_payload_id(pid)

    # alter state to allow a new workflow execution of the same payload
    wfem.aborted(pid, execution_arn=sfn_exe1["executionArn"])

    # Create a new PayloadManagers object so it fetches fresh state
    basic_payload_managers2 = basic_payload_managers_factory()
    basic_payload_managers2.process(wfem)
    sfn_exe2 = deployment.get_execution_by_payload_id(pid)
    assert sfn_exe1["executionArn"] != sfn_exe2["executionArn"]


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


def test_get_workflow_summary(deployment, create_records, statedb):
    result = deployment("get-workflow-summary sar-test-panda test")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    assert output["collections"] == "sar-test-panda"
    assert output["workflow"] == "test"
    assert "counts" in output

    expected_states = [
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "INVALID",
        "ABORTED",
        "CLAIMED",
    ]
    for state in expected_states:
        assert state in output["counts"]
        if state in ["COMPLETED", "FAILED"]:
            assert output["counts"][state] == 2
        else:
            assert output["counts"][state] == 0


def test_get_workflow_summary_with_since_option(deployment, create_records, statedb):
    result = deployment(
        "get-workflow-summary sar-test-panda test --since 1d",
    )
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    expected_states = [
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "INVALID",
        "ABORTED",
        "CLAIMED",
    ]
    for state in expected_states:
        if state == "COMPLETED":
            assert output["counts"][state] == 2
        elif state == "FAILED":
            assert output["counts"][state] == 1
        else:
            assert output["counts"][state] == 0


def test_get_workflow_summary_with_limit_option(deployment, create_records, statedb):
    result = deployment(
        "get-workflow-summary sar-test-panda test --limit 1",
    )
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    expected_states = [
        "PROCESSING",
        "COMPLETED",
        "FAILED",
        "INVALID",
        "ABORTED",
        "CLAIMED",
    ]
    for state in expected_states:
        count = output["counts"][state]
        assert count == 0 or count == 1 or count == "1+"


def test_get_workflow_stats(deployment, put_parameters):
    # we can't query timestream db data with moto, so just check the output structure
    result = deployment("get-workflow-stats")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    # Verify the expected output structure
    assert "state_transitions" in output
    assert "daily" in output["state_transitions"]
    assert "hourly" in output["state_transitions"]
    assert "hourly_rolling" in output["state_transitions"]

    # Each should be a list
    assert isinstance(output["state_transitions"]["daily"], list)
    assert isinstance(output["state_transitions"]["hourly"], list)
    assert isinstance(output["state_transitions"]["hourly_rolling"], list)


def test_get_workflow_items(deployment, create_records, statedb):
    result = deployment("get-workflow-items sar-test-panda test")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    assert "items" in output
    assert isinstance(output["items"], list)
    assert len(output["items"]) == 4


def test_get_workflow_items_with_state_filter(deployment, create_records, statedb):
    result = deployment("get-workflow-items sar-test-panda test --state COMPLETED")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    assert len(output["items"]) == 2
    for item in output["items"]:
        assert item["state"] == "COMPLETED"


def test_get_workflow_items_with_since_option(deployment, create_records, statedb):
    result = deployment("get-workflow-items sar-test-panda test --since 1d")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    assert len(output["items"]) == 3


def test_get_workflow_items_with_limit_option(deployment, create_records, statedb):
    result = deployment("get-workflow-items sar-test-panda test --limit 2")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    assert len(output["items"]) == 2


def test_get_workflow_items_with_nextkey_option(deployment, create_records, statedb):
    # Get first item (descending order by default) and use its payload_id as nextkey
    result = deployment("get-workflow-items sar-test-panda test --limit 1")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())
    payload_id = output["items"][0]["payload_id"]

    # make sure we got the expected first item per the fixture
    assert payload_id == create_records["failed"][1]

    # Get the next page using nextkey
    result = deployment(
        f"get-workflow-items sar-test-panda test --nextkey {payload_id} --limit 1",
    )
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    # Check that the item returned in the page is expected per the fixture
    assert output["items"][0]["payload_id"] == create_records["failed"][0]


def test_get_workflow_items_with_sort_ascending_option(
    deployment,
    create_records,
    statedb,
):
    # default is descending
    result = deployment("get-workflow-items sar-test-panda test")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())
    assert output["items"][0]["payload_id"] == create_records["failed"][1]

    # test ascending
    result = deployment("get-workflow-items sar-test-panda test --sort-ascending")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())
    assert output["items"][0]["payload_id"] == create_records["completed"][0]


def test_get_workflow_items_with_sort_index_option(deployment, create_records, statedb):
    # The default index is "updated"; the only other sort index is "state_updated"
    result = deployment(
        "get-workflow-items sar-test-panda test --sort-index state_updated",
    )
    assert result.exit_code == 0


def test_get_workflow_item(deployment, create_records, statedb):
    # Use one of the completed items from our test data
    result = deployment("get-workflow-item sar-test-panda test completed-0")
    assert result.exit_code == 0
    output = json.loads(result.stdout.strip())

    assert output["item"]["collections"] == "sar-test-panda"
    assert output["item"]["workflow"] == "test"
    assert output["item"]["items"] == "completed-0"
