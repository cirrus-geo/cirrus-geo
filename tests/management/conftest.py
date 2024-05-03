import json
import shlex

from unittest.mock import patch

import boto3
import botocore.client
import moto
import pytest

from cirrus.lib.process_payload import ProcessPayload, ProcessPayloads
from cirrus.management.cli import cli
from click.testing import CliRunner


@pytest.fixture()
def timestream_write_client():
    with moto.mock_timestreamwrite():
        yield boto3.client("timestream-write", region_name="us-east-1")


# moto does not mock lambda GetFunctionConfiguration
# see https://docs.getmoto.org/en/latest/docs/services/patching_other_services.html
orig = botocore.client.BaseClient._make_api_call

LAMBDA_ENV_VARS = {"var": "value"}


@pytest.fixture()
def lambda_env():
    return LAMBDA_ENV_VARS


def mock_make_api_call(self, operation_name, kwarg):
    if operation_name == "GetFunctionConfiguration":
        return {"Environment": {"Variables": LAMBDA_ENV_VARS}}
    return orig(self, operation_name, kwarg)


@pytest.fixture()
def mock_lambda_get_conf():  # noqa: PT004
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
