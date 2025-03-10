import json
import shlex

from pathlib import Path
from unittest.mock import patch

import boto3
import botocore.client
import moto
import pytest

from cirrus.lib.process_payload import ProcessPayload, ProcessPayloads
from cirrus.management.cli import cli
from cirrus.management.deployment_pointer import DEPLOYMENTS_PREFIX
from click.testing import CliRunner


@pytest.fixture()
def timestream_write_client():
    with moto.mock_timestreamwrite():
        yield boto3.client("timestream-write", region_name="us-east-1")


# moto does not mock lambda GetFunctionConfiguration
# see https://docs.getmoto.org/en/latest/docs/services/patching_other_services.html
orig = botocore.client.BaseClient._make_api_call

LAMBDA_ENV_VARS = {"var": "value"}

PAYLOADS = Path(__file__).parent / "fixtures"


@pytest.fixture()
def lambda_env():
    return LAMBDA_ENV_VARS


def mock_make_api_call(self, operation_name, kwarg):
    if operation_name == "GetFunctionConfiguration":
        return {"Environment": {"Variables": LAMBDA_ENV_VARS}}
    return orig(self, operation_name, kwarg)


@pytest.fixture()
def _mock_lambda_get_conf():
    with patch(
        "botocore.client.BaseClient._make_api_call",
        new=mock_make_api_call,
    ):
        yield


@pytest.fixture(scope="session")
def cli_runner():
    return CliRunner(mix_stderr=False)


@pytest.fixture(scope="session")
def invoke(cli_runner):
    def _invoke(cmd, **kwargs):
        kwargs["catch_exceptions"] = kwargs.get("catch_exceptions", False)
        return cli_runner.invoke(cli, shlex.split(cmd), **kwargs)

    return _invoke


@pytest.fixture()
def basic_payloads(fixtures, statedb):
    return ProcessPayloads(
        process_payloads=[
            ProcessPayload(
                json.loads(fixtures.joinpath("basic_payload.json").read_text()),
            ),
        ],
        statedb=statedb,
    )


def mock_parameters(queue, payloads, statedb, workflow, deployment_name):
    return {
        "CIRRUS_PAYLOAD_BUCKET": payloads,
        "CIRRUS_BASE_WORKFLOW_ARN": workflow["stateMachineArn"].replace(
            "workflow1",
            "",
        ),
        "CIRRUS_PROCESS_QUEUE_URL": queue["QueueUrl"],
        "CIRRUS_STATE_DB": statedb.table_name,
        "CIRRUS_PREFIX": f"fd-{deployment_name}-dev-cirrus-",
    }


@pytest.fixture()
def put_parameters(ssm, queue, payloads, statedb, workflow):
    for deployment_name in ["lion", "squirrel-dev"]:
        # put pointer parameters
        deployment_key = f"/deployment/{deployment_name}/"
        ssm.put_parameter(
            Name=f"{DEPLOYMENTS_PREFIX}{deployment_name}",
            Value=json.dumps(
                {
                    "type": "parameter_store",
                    "value": deployment_key,
                },
            ),
            Type="String",
        )
        # put mock deployment parameters
        for param_name, value in mock_parameters(
            queue,
            payloads,
            statedb,
            workflow,
            deployment_name,
        ).items():
            name = f"{deployment_key}{param_name}"
            ssm.put_parameter(
                Name=name,
                Value=value,
                Type="String",
            )
    return ssm


@pytest.fixture()
def make_lambdas(lambdas, iam_role):
    lambda_code = """
    def lambda_handler(event, context):
        return
    """
    lambdas.create_function(
        FunctionName="fd-lion-dev-cirrus-process",
        Runtime="python3.12",
        Role=iam_role,
        Code={"ZipFile": bytes(lambda_code, "utf-8")},
        Description="mock process lambda for unit testing",
    )
    return lambdas
