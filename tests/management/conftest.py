import json
import shlex

from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import patch

import botocore.client
import pytest

from click.testing import CliRunner

from cirrus.lib.payload_manager import PayloadManager, PayloadManagers
from cirrus.management.cli import cli
from cirrus.management.deployment_pointer import DEPLOYMENTS_PREFIX

# moto does not mock lambda GetFunctionConfiguration
# see https://docs.getmoto.org/en/latest/docs/services/patching_other_services.html
orig = botocore.client.BaseClient._make_api_call

LAMBDA_ENV_VARS = {"var": "value"}


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
    def upload_mock_payload(bucket_name: str, payload_id: str):
        payload = {
            "payload_id": payload_id,
            "process": [{"workflow": "test"}],
            "properties": {"a": "property"},
        }
        with BytesIO() as f:
            f.write(json.dumps(payload, indent=4).encode("utf-8"))
            f.seek(0)
            s3.upload_fileobj(f, bucket_name, f"{payload_id}/input.json")

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
    for index, id in enumerate(payload_ids["completed"]):
        (
            statedb.claim_processing(
                id,
                st_func_execution_arn,
            ),
        )
        statedb.set_completed(
            id,
            [f"item-{id}_completed-{index}"],
        )
        upload_mock_payload(payloads, id)
    for index, id in enumerate(payload_ids["failed"]):
        statedb.set_failed(
            id,
            f"failed-error-message-{index}",
            (datetime.now(UTC) + timedelta(days=index)).isoformat(),
        )
        upload_mock_payload(payloads, id)

    return payload_ids
