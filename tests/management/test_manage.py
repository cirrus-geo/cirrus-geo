import json

import pytest

from cirrus.management.deployment import (
    Deployment,
)

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
def deployment(manage, queue, payloads, statedb, workflow, iam_role):
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


def test_manage_show_deployment(deployment, put_parameters):
    result = deployment("show")
    assert result.exit_code == 0
    assert result.stdout.strip() == json.dumps(deployment.environment, indent=4)


def test_manage_show_unknown_deployment(manage, put_parameters):
    unknown = "unknown-deployment"
    result = manage(f"{unknown} show")
    assert result.exit_code == 1
    assert result.stderr.strip() == f"Deployment not found: '{unknown}'"


def test_list_deployments(invoke, put_parameters):
    result = invoke("list-deployments")
    assert result.exit_code == 0
    assert result.stdout.strip().splitlines() == ["lion", "squirrel-dev"]


def test_list_lambas(deployment, make_lambdas, put_parameters):
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


def test_get_execution_by_arn(deployment, st_func_execution_arn):
    result = deployment(
        f"get-execution --arn {st_func_execution_arn}",
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout.strip())["executionArn"] == st_func_execution_arn


@pytest.mark.xfail()
def test_process(deployment, manage, make_lambdas):
    result = deployment('process {"a": "payload to test process command"}')
    assert result.exit_code == 0
    assert result.stdout.strip == json.dumps('{"a": "check"}')


@pytest.mark.xfail()
@pytest.mark.usefixtures("_mock_lambda_get_conf")
def test_manage_refresh(deployment, lambda_env):
    result = deployment("refresh")
    assert result.exit_code == 0
    new = json.loads(deployment("show").stdout)
    assert new["environment"] == lambda_env


@pytest.mark.xfail()
@pytest.mark.usefixtures("_environment")
def test_manage_get_execution_by_payload_id(
    deployment,
    basic_payloads,
    statedb,
    wfem,
    put_parameters,
    st_func_execution_arn,
) -> None:
    """Adds causes two workflow executions, and confirms that the second call
    to get_execution_by_payload_id gets a different executionArn value from the
    first execution."""
    basic_payloads.process(wfem)
    pid = basic_payloads[0]["id"]
    sfn_exe1 = deployment.get_execution_by_payload_id(pid)
    statedb.set_aborted(pid, execution_arn=sfn_exe1["executionArn"])
    basic_payloads.process(wfem)
    sfn_exe2 = deployment.get_execution_by_payload_id(pid)
    assert sfn_exe1["executionArn"] != sfn_exe2["executionArn"]


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
