import json

import pytest

from cirrus.management.deployment import (
    Deployment,
)
from click.testing import Result

from tests.management.conftest import mock_parameters

MOCK_DEPLYOMENT_NAME = "lion"
STACK_NAME = "cirrus-test"
MOCK_CIRRUS_PREFIX = "ts-lion-dev-cirrus"


@pytest.fixture()
def manage(invoke):
    def _manage(cmd):
        return invoke("manage " + cmd)

    return _manage


@pytest.fixture()
def deployment(manage, queue, payloads, statedb, workflow, sts, iam_role):
    def _manage(deployment, cmd):
        return manage(f"{deployment.name} {cmd}")

    Deployment.__call__ = _manage

    return Deployment(
        MOCK_DEPLYOMENT_NAME,
        mock_parameters(
            queue,
            payloads,
            statedb,
            workflow,
            MOCK_DEPLYOMENT_NAME,
            iam_role,
        ),
    )


def test_manage(manage):
    result = manage("")
    assert result.exit_code == 0


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


# using non-stac payloads for simplier testing
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


def test_list_lambas(deployment, make_lambdas, put_parameters, iam_role):
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


@pytest.mark.xfail()
def test_process(deployment, manage, make_lambdas):
    result = deployment('process {"a": "payload to test process command"}')
    assert result.exit_code == 0
    assert result.stdout.strip == json.dumps('{"a": "check"}')


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
            "--since '10 d' --state 'COMPLETED'",
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
