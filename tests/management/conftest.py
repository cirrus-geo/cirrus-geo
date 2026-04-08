import json
import os
import shlex

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import botocore.client
import pytest

from click.testing import CliRunner

from cirrus.lib.payload_bucket import PayloadBucket
from cirrus.lib.payload_manager import PayloadManager, PayloadManagers
from cirrus.lib.statedb import StateDB
from cirrus.management.cli import cli
from cirrus.management.deployment import Deployment
from cirrus.management.deployment_pointer import DEPLOYMENTS_PREFIX

MOCK_DEPLOYMENT_NAME = "lion"

# moto does not mock lambda GetFunctionConfiguration
# see https://docs.getmoto.org/en/latest/docs/services/patching_other_services.html
orig = botocore.client.BaseClient._make_api_call

LAMBDA_ENV_VARS = {"var": "value"}


@pytest.fixture(autouse=True)
def _isolated_env(_environment):
    os.environ.clear()
    os.environ.update(
        {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SECURITY_TOKEN": "testing",
            "AWS_SESSION_TOKEN": "testing",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_REGION": "us-east-1",
        },
    )


@pytest.fixture
def lambda_env():
    return LAMBDA_ENV_VARS


def mock_make_api_call(self, operation_name, kwarg):
    if operation_name == "GetFunctionConfiguration":
        return {"Environment": {"Variables": LAMBDA_ENV_VARS}}
    return orig(self, operation_name, kwarg)


@pytest.fixture
def _mock_lambda_get_conf():
    with patch(
        "botocore.client.BaseClient._make_api_call",
        new=mock_make_api_call,
    ):
        yield


@pytest.fixture(scope="session")
def cli_runner():
    return CliRunner()


@pytest.fixture(scope="session")
def invoke(cli_runner):
    def _invoke(cmd, **kwargs):
        kwargs["catch_exceptions"] = kwargs.get("catch_exceptions", False)
        return cli_runner.invoke(cli, shlex.split(cmd), **kwargs)

    return _invoke


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


@pytest.fixture
def basic_payload_managers_factory(fixtures, statedb):
    def _create_basic_payload_managers():
        return PayloadManagers(
            payload_managers=[
                PayloadManager(
                    json.loads(fixtures.joinpath("basic_payload.json").read_text()),
                ),
            ],
            statedb=statedb,
        )

    return _create_basic_payload_managers


def mock_parameters(
    queue,
    payloads,
    data,
    statedb,
    workflow,
    deployment_name,
    iam_role,
):
    return {
        "CIRRUS_PAYLOAD_BUCKET": payloads,
        "CIRRUS_BASE_WORKFLOW_ARN": workflow["stateMachineArn"].replace(
            "test-workflow1",
            "",
        ),
        "CIRRUS_PROCESS_QUEUE_URL": queue["QueueUrl"],
        "CIRRUS_STATE_DB": statedb.table_name,
        "CIRRUS_EVENT_DB_AND_TABLE": "event-db-1|event-table-1",
        "CIRRUS_PREFIX": f"fd-{deployment_name}-dev-cirrus-",
        "CIRRUS_CLI_IAM_ARN": iam_role,
    }


@pytest.fixture
def put_parameters(ssm, queue, payloads, data, statedb, workflow, iam_role):
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
            data,
            statedb,
            workflow,
            deployment_name,
            iam_role,
        ).items():
            name = f"{deployment_key}{param_name}"
            ssm.put_parameter(
                Name=name,
                Value=value,
                Type="String",
            )
    return ssm


@pytest.fixture
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


@pytest.fixture
def create_records(
    s3,
    put_parameters,
    statedb,
    payloads,
    st_func_execution_arn,
):
    payload_bucket = PayloadBucket(bucket_name=payloads)

    def gen_mock_payload(payload_id: str) -> dict[str, Any]:
        return {
            "payload_id": payload_id,
            "process": [{"workflow": "test"}],
            "properties": {"a": "property"},
        }

    payload_ids = {
        "completed": [
            "sar-test-panda/workflow-test/completed-0",
            "sar-test-panda/workflow-test/completed-1",
        ],
        "failed": [
            "sar-test-panda/workflow-test/failed-0",
            "sar-test-panda/workflow-test/failed-1",
        ],
    }

    # add to mock statedb first then to mock payload bucket
    # claim_processing to set execution arn needed in tests
    for index, payload_id in enumerate(payload_ids["completed"]):
        statedb.claim_processing(payload_id, st_func_execution_arn)
        statedb.set_succeeded(
            payload_id,
            [f"item-{id}_completed-{index}"],
        )
        payload = gen_mock_payload(payload_id)
        payload_bucket.upload_input_payload(
            payload,
            payload_id,
            StateDB.execution_id_from_arn(st_func_execution_arn),
        )
        payload_bucket.upload_output_payload(
            payload,
            payload_id,
            StateDB.execution_id_from_arn(st_func_execution_arn),
        )
    for index, payload_id in enumerate(payload_ids["failed"]):
        statedb.claim_processing(payload_id, st_func_execution_arn)
        statedb.set_failed(
            payload_id,
            f"failed-error-message-{index}",
            (datetime.now(UTC) + timedelta(days=index)).isoformat(),
        )
        payload = gen_mock_payload(payload_id)
        payload_bucket.upload_input_payload(
            payload,
            payload_id,
            StateDB.execution_id_from_arn(st_func_execution_arn),
        )

    return payload_ids
