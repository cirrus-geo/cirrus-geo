import json
import os
from pathlib import Path
from typing import Any, Dict

import boto3
import moto
import pytest

from cirrus.lib2.eventdb import EventDB
from cirrus.lib2.statedb import StateDB


def set_fake_creds():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_REGION"] = "us-east-1"


set_fake_creds()


@pytest.fixture(autouse=True)
def aws_credentials():
    set_fake_creds()


@pytest.fixture(scope="session")
def fixtures():
    return Path(__file__).parent.joinpath("fixtures")


@pytest.fixture(scope="session")
def statedb_schema(fixtures) -> Dict[str, Any]:
    return json.loads(fixtures.joinpath("statedb-schema.json").read_text())


@pytest.fixture
def dynamo(aws_credentials):
    with moto.mock_dynamodb():
        yield boto3.client("dynamodb", region_name="us-east-1")


@pytest.fixture
def statedb_table_name(dynamo, statedb_schema) -> str:
    dynamo.create_table(**statedb_schema)
    return statedb_schema["TableName"]


@pytest.fixture
def timestream_write_client():
    with moto.mock_timestreamwrite():
        yield boto3.client("timestream-write", region_name="us-east-1")


@pytest.fixture
def eventdb(timestream_write_client) -> EventDB:
    timestream_write_client.create_database(DatabaseName="event-db-1")
    timestream_write_client.create_table(
        DatabaseName="event-db-1", TableName="event-table-1"
    )
    return EventDB("event-db-1|event-table-1")


@pytest.fixture
def statedb(dynamo, statedb_schema, eventdb) -> str:
    dynamo.create_table(**statedb_schema)
    table_name = statedb_schema["TableName"]
    return StateDB(table_name=table_name)
