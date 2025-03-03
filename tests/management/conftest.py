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
from cirrus.management.deployment_pointer import PARAMETER_PREFIX
from click.testing import CliRunner

from tests.conftest import MOCK_REGION


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


@pytest.fixture()
def parameter_store_response():
    with Path.open(PAYLOADS / "parameter_store_response.json") as f:
        return json.load(f)["Parameters"]


def mock_parameters(deployment_name: str, region: str = MOCK_REGION):
    return {
        "CIRRUS_BASE_WORKFLOW_ARN": f"arn:aws:states:{region}:00000000:stateMachine:fd-{deployment_name}-dev-cirrus-",
        "CIRRUS_DATA_BUCKET": f"filmdrop-{deployment_name}-{region}-random-data-bucket-name",
        "CIRRUS_EVENT_DB_AND_TABLE": f"fd-{deployment_name}-dev-cirrus-nane-db|fd-{deployment_name}-dev-cirrus-random-table",
        "CIRRUS_LOG_LEVEL": "DEBUG",
        "CIRRUS_PAYLOAD_BUCKET": f"filmdrop-{deployment_name}-{region}-cirrus-random-payload-bucket-000000",
        "CIRRUS_PREFIX": f"fd-{deployment_name}-dev-cirrus",
        "CIRRUS_PROCESS_QUEUE_URL": f"https://sqs.{region}.amazonaws.com/000000000/fd-{deployment_name}-dev-cirrus-random-queue-name",
        "CIRRUS_STATE_DB": f"fd-{deployment_name}-dev-cirrus-random-state-db",
        "CIRRUS_WORKFLOW_EVENT_TOPIC_ARN": f"arn:aws:sns:{region}:00000000000:fd-{deployment_name}-dev-cirrus-random-workflow-name-here",
    }


@pytest.fixture()
def put_parameters(ssm):
    # don't want slashes in parameter arn values but want in param path
    for deployment_name in ["lion", "squirrel/dev"]:
        for param_name, value in mock_parameters(deployment_name.split("/")[0]).items():
            ssm.put_parameter(
                Name=f"{PARAMETER_PREFIX}{deployment_name}/{param_name}",
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
