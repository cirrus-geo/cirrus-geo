import json

import boto3
import pytest

from cirrus.management.deployment import (
    CONFIG_VERSION,
    DEFAULT_DEPLOYMENTS_DIR_NAME,
    Deployment,
    DeploymentPointer,
)

DEPLYOMENT_NAME = "test-deployment"
STACK_NAME = "cirrus-test"


@pytest.fixture()
def manage(invoke):
    def _manage(cmd):
        return invoke("manage " + cmd)

    return _manage


@pytest.fixture()
def deployment_meta(queue, statedb, payloads, data, workflow):
    return {
        "name": DEPLYOMENT_NAME,
        "created": "2022-11-07T04:42:26.666916+00:00",
        "updated": "2022-11-07T04:42:26.666916+00:00",
        "stackname": STACK_NAME,
        "profile": None,
        "environment": {
            "CIRRUS_STATE_DB": statedb.table_name,
            "CIRRUS_BASE_WORKFLOW_ARN": workflow["stateMachineArn"].replace(
                "workflow1",
                "",
            ),
            "CIRRUS_LOG_LEVEL": "DEBUG",
            "CIRRUS_STACK": STACK_NAME,
            "CIRRUS_DATA_BUCKET": data,
            "CIRRUS_PAYLOAD_BUCKET": payloads,
            "CIRRUS_PROCESS_QUEUE_URL": queue["QueueUrl"],
        },
        "user_vars": {},
        "config_version": CONFIG_VERSION,
    }


@pytest.fixture()
def deployment(manage, project, deployment_meta):
    def _manage(deployment, cmd):
        return manage(f"{deployment.name} {cmd}")

    Deployment.__call__ = _manage

    dep = Deployment(
        Deployment.get_path_from_project(project, DEPLYOMENT_NAME),
        **deployment_meta,
    )
    dep.save()

    yield dep

    Deployment.remove(dep.name, project)


def test_manage(manage):
    result = manage("")
    assert result.exit_code == 0


@pytest.mark.xfail()
def test_manage_show_deployment(deployment, deployment_meta):
    result = deployment("show")
    assert result.exit_code == 0
    assert result.stdout.strip() == json.dumps(deployment_meta, indent=4)


@pytest.mark.xfail()
def test_manage_show_unknown_deployment(manage, deployment):
    unknown = "unknown-deployment"
    result = manage(f"{unknown} show")
    assert result.exit_code == 1
    assert result.stderr.strip() == f"Deployment not found: {unknown}"


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
def test_manage_refresh(deployment, mock_lambda_get_conf, lambda_env):
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


@pytest.mark.xfail()
@pytest.mark.parametrize(
    ("command", "expect_exit_zero"),
    [
        ("true", True),
        ("false", False),
    ],
)
def test_call_cli_return_values(deployment, command, expect_exit_zero):
    result = deployment(f"call {command}")
    assert result.exit_code == 0 if expect_exit_zero else result.exit_code != 0


def test_parse_deployments(parameter_store_response):
    actual = DeploymentPointer.parse_deployments(
        parameter_store_response,
        "/cirrus/deployments/",
    )
    expected = [
        DeploymentPointer(
            "/cirrus/deployments/",
            "rhino",
            {
                "dlq-url": "cirrus-rhino-dlq-url",
                "payload-bucket": "arn:s3:rhino-payload-bucket",
                "process-lambda": "cirrus-rhino-process-lambda",
            },
        ),
        DeploymentPointer(
            "/cirrus/deployments/",
            "squirrel/dev",
            {
                "payload-bucket": "arn::s3:a-bucket-for-payload",
                "process-lambda": "cirrus-squirrel-process-lambda",
            },
        ),
    ]
    assert actual == expected


def test_get_deployments(parameter_store):
    deployments = DeploymentPointer._get_deployments(
        "/cirrus/deployments/",
        region="us-west-2",
        session=boto3.Session(),
    )
    expected = [
        DeploymentPointer(
            "/cirrus/deployments/",
            "rhino",
            {
                "dlq-url": "cirrus-rhino-dlq-url",
                "payload-bucket": "arn:s3:rhino-payload-bucket",
                "process-lambda": "cirrus-rhino-process-lambda",
            },
        ),
        DeploymentPointer(
            "/cirrus/deployments/",
            "squirrel/dev",
            {
                "payload-bucket": "arn::s3:a-bucket-for-payload",
                "process-lambda": "cirrus-squirrel-process-lambda",
            },
        ),
    ]
    assert deployments == expected


def test_get_deployment_by_name(parameter_store):
    deployment = DeploymentPointer.get_deployment_by_name(
        "rhino",
        "/cirrus/deployments/",
        "us-west-2",
        boto3.Session(),
    )
    assert deployment == DeploymentPointer(
        "/cirrus/deployments/",
        "rhino",
        {
            "dlq-url": "cirrus-rhino-dlq-url",
            "payload-bucket": "arn:s3:rhino-payload-bucket",
            "process-lambda": "cirrus-rhino-process-lambda",
        },
    )
