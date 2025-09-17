import json
import os

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import moto
import pytest

from click.testing import CliRunner

from cirrus.lib.eventdb import EventDB
from cirrus.lib.events import WorkflowEventManager
from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import get_client

MOCK_REGION = "us-east-1"


def set_fake_creds():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"  # noqa: S105
    os.environ["AWS_SECURITY_TOKEN"] = "testing"  # noqa: S105
    os.environ["AWS_SESSION_TOKEN"] = "testing"  # noqa: S105
    os.environ["AWS_DEFAULT_REGION"] = MOCK_REGION
    os.environ["AWS_REGION"] = MOCK_REGION


set_fake_creds()


@pytest.fixture(autouse=True)
def _aws_credentials():
    set_fake_creds()


@pytest.fixture(scope="session")
def fixtures():
    return Path(__file__).parent.joinpath("fixtures")


@pytest.fixture(scope="session")
def statedb_schema(fixtures) -> dict[str, Any]:
    return json.loads(fixtures.joinpath("statedb-schema.json").read_text())


@pytest.fixture
def s3():
    with moto.mock_aws():
        yield get_client("s3", region=MOCK_REGION)


@pytest.fixture
def sqs():
    with moto.mock_aws():
        yield get_client("sqs", region=MOCK_REGION)


@pytest.fixture
def sns():
    with moto.mock_aws():
        yield get_client("sns", region=MOCK_REGION)


@pytest.fixture
def ssm():
    with moto.mock_aws():
        yield get_client("ssm", region=MOCK_REGION)


@pytest.fixture
def sts():
    with moto.mock_aws():
        yield get_client("sts", region=MOCK_REGION)


@pytest.fixture
def lambdas():
    with moto.mock_aws():
        yield get_client("lambda", region=MOCK_REGION)


@pytest.fixture
def dynamo():
    with moto.mock_aws():
        yield get_client("dynamodb", region=MOCK_REGION)


@pytest.fixture
def stepfunctions():
    with moto.mock_aws():
        yield get_client("stepfunctions", region=MOCK_REGION)


@pytest.fixture
def iam():
    with moto.mock_aws():
        yield get_client("iam", region=MOCK_REGION)


@pytest.fixture
def timestream_write_client():
    with moto.mock_aws():
        yield get_client("timestream-write", region=MOCK_REGION)


@pytest.fixture
def eventdb(timestream_write_client) -> EventDB:
    timestream_write_client.create_database(DatabaseName="event-db-1")
    timestream_write_client.create_table(
        DatabaseName="event-db-1",
        TableName="event-table-1",
    )
    return EventDB("event-db-1|event-table-1")


@pytest.fixture
def statedb(dynamo, statedb_schema, eventdb) -> StateDB:
    dynamo.create_table(**statedb_schema)
    table_name = statedb_schema["TableName"]
    return StateDB(table_name=table_name)


@pytest.fixture
def payloads(s3):
    name = "payloads"
    s3.create_bucket(Bucket=name)
    return name


@pytest.fixture
def data(s3):
    name = "data"
    s3.create_bucket(Bucket=name)
    return name


@pytest.fixture
def queue(sqs):
    q = sqs.create_queue(QueueName="test-queue")
    q["Arn"] = f"arn:aws:sqs:{MOCK_REGION}:123456789012:test-queue"
    return q


@pytest.fixture
def iam_role(iam):
    role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": f"states.{MOCK_REGION}.amazonaws.com",
                },
                "Action": "sts:AssumeRole",
            },
        ],
    }
    role = iam.create_role(
        RoleName="test-step-function-role",
        AssumeRolePolicyDocument=json.dumps(role_policy),
    )["Role"]

    return role["Arn"]


@pytest.fixture
def workflow(stepfunctions, iam_role):
    defn = {
        "StartAt": "FirstState",
        "States": {
            "FirstState": {
                "Type": "Pass",
                "End": True,
            },
        },
    }
    return stepfunctions.create_state_machine(
        name="test-workflow1",
        definition=json.dumps(defn),
        roleArn=iam_role,
    )


@pytest.fixture
def _environment() -> Iterator[None]:
    current_env = deepcopy(os.environ)  # stash env
    try:
        yield
    finally:
        os.environ.clear()
        os.environ = current_env  # noqa: B003


@pytest.fixture
def execute_state_machine(stepfunctions, workflow, put_parameters):
    state_machine_arn = workflow["stateMachineArn"]
    os.environ["CIRRUS_BASE_WORKFLOW_ARN"] = state_machine_arn[: -len("test-workflow1")]
    return stepfunctions.start_execution(
        stateMachineArn=state_machine_arn,
        name="test-execution",
    )


@pytest.fixture
def st_func_execution_arn(execute_state_machine):
    return execute_state_machine["executionArn"]


@pytest.fixture
def wfem(statedb, eventdb):
    return WorkflowEventManager(statedb=statedb, eventdb=eventdb)


@pytest.fixture
def runner():
    return CliRunner()
