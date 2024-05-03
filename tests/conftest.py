import json
import os

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import moto
import pytest

from cirrus.lib.eventdb import EventDB
from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import get_client


def set_fake_creds():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"  # noqa: S105
    os.environ["AWS_SECURITY_TOKEN"] = "testing"  # noqa: S105
    os.environ["AWS_SESSION_TOKEN"] = "testing"  # noqa: S105
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_REGION"] = "us-east-1"


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


@pytest.fixture()
def s3():
    with moto.mock_s3():
        yield get_client("s3", region="us-east-1")


@pytest.fixture()
def sqs():
    with moto.mock_sqs():
        yield get_client("sqs", region="us-east-1")


@pytest.fixture()
def sns():
    with moto.mock_sns():
        yield get_client("sns", region="us-east-1")


@pytest.fixture()
def dynamo():
    with moto.mock_dynamodb():
        yield get_client("dynamodb", region="us-east-1")


@pytest.fixture()
def stepfunctions():
    with moto.mock_stepfunctions():
        yield get_client("stepfunctions", region="us-east-1")


@pytest.fixture()
def iam():
    with moto.mock_iam():
        yield get_client("iam", region="us-east-1")


@pytest.fixture()
def statedb_table_name(dynamo, statedb_schema) -> str:
    dynamo.create_table(**statedb_schema)
    return statedb_schema["TableName"]


@pytest.fixture()
def timestream_write_client():
    with moto.mock_timestreamwrite():
        yield get_client("timestream-write", region="us-east-1")


@pytest.fixture()
def eventdb(timestream_write_client) -> EventDB:
    timestream_write_client.create_database(DatabaseName="event-db-1")
    timestream_write_client.create_table(
        DatabaseName="event-db-1",
        TableName="event-table-1",
    )
    return EventDB("event-db-1|event-table-1")


@pytest.fixture()
def statedb(dynamo, statedb_schema, eventdb) -> StateDB:
    dynamo.create_table(**statedb_schema)
    table_name = statedb_schema["TableName"]
    return StateDB(table_name=table_name)


@pytest.fixture()
def payloads(s3):
    name = "payloads"
    s3.create_bucket(Bucket=name)
    return name


@pytest.fixture()
def data(s3):
    name = "data"
    s3.create_bucket(Bucket=name)
    return name


@pytest.fixture()
def queue(sqs):
    q = sqs.create_queue(QueueName="test-queue")
    q["Arn"] = "arn:aws:sqs:us-east-1:123456789012:test-queue"
    return q


@pytest.fixture()
def workflow(stepfunctions, iam):
    defn = {
        "StartAt": "FirstState",
        "States": {
            "FirstState": {
                "Type": "Pass",
                "End": True,
            },
        },
    }
    role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "states.us-east-1.amazonaws.com",
                },
                "Action": "sts:AssumeRole",
            },
        ],
    }
    role = iam.create_role(
        RoleName="test-step-function-role",
        AssumeRolePolicyDocument=json.dumps(role_policy),
    )["Role"]
    return stepfunctions.create_state_machine(
        name="test-workflow1",
        definition=json.dumps(defn),
        roleArn=role["Arn"],
    )


@pytest.fixture()
def _environment() -> Iterator[None]:
    current_env = deepcopy(os.environ)  # stash env
    try:
        yield
    finally:
        os.environ.clear()
        os.environ = current_env  # noqa: B003
