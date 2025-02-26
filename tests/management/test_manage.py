import json

from dataclasses import asdict

import pytest

from cirrus.management.deployment import (
    CONFIG_VERSION,
    DEFAULT_DEPLOYMENTS_DIR_NAME,
    Deployment,
    DeploymentMeta,
)
from cirrus.management.deployment_pointer import PARAMETER_PREFIX

from tests.management.conftest import mock_parameters

DEPLYOMENT_NAME = "lion"
STACK_NAME = "cirrus-test"
MOCK_CIRRUS_PREFIX = "ts-lion-dev-cirrus"


@pytest.fixture()
def manage(invoke):
    def _manage(cmd):
        return invoke("manage " + cmd)

    return _manage


@pytest.fixture()
def deployment_meta() -> DeploymentMeta:
    return DeploymentMeta(
        name=DEPLYOMENT_NAME,
        prefix=PARAMETER_PREFIX,
        environment=mock_parameters(DEPLYOMENT_NAME),
        user_vars={},
        config_version=CONFIG_VERSION,
    )


@pytest.fixture()
def deployment(manage, deployment_meta):
    def _manage(deployment, cmd):
        return manage(f"{deployment.name} {cmd}")

    Deployment.__call__ = _manage

    return Deployment(
        **asdict(deployment_meta),
    )


def test_manage(manage):
    result = manage("")
    assert result.exit_code == 0


def test_manage_show_deployment(deployment, deployment_meta, put_parameters):
    result = deployment("show")
    assert result.exit_code == 0
    assert result.stdout.strip() == json.dumps(asdict(deployment_meta), indent=4)


def test_manage_show_unknown_deployment(manage, put_parameters):
    unknown = "unknown-deployment"
    result = manage(f"{unknown} show")
    assert result.exit_code == 1
    assert (
        result.stderr.strip()
        == f"Deployment not found: no deployment named '{unknown}' was found in the parameter store"
    )


def test_list_lambas(deployment, manage, make_lambdas, put_parameters):
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


def test_process(deployment, manage, make_lambdas):
    result = deployment('process {"a": "payload to test process command"}')
    assert result.exit_code == 0
    assert result.stdout.strip == json.dumps('{"a": "check"}')


@pytest.mark.xfail()
def test_manage_get_path(deployment, project):
    result = deployment("get-path")
    assert result.exit_code == 0
    assert result.stdout.strip() == str(
        project.dot_dir.joinpath(
            DEFAULT_DEPLOYMENTS_DIR_NAME,
            f"{DEPLYOMENT_NAME}.json",
        ),
    )


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
) -> None:
    """Adds causes two workflow executions, and confirms that the second call
    to get_execution_by_payload_id gets a different executionArn value from the
    first execution."""
    deployment.set_env()
    basic_payloads.process()
    pid = basic_payloads[0]["id"]
    sfn_exe1 = deployment.get_execution_by_payload_id(pid)
    statedb.set_aborted(pid, execution_arn=sfn_exe1["executionArn"])
    basic_payloads.process()
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
