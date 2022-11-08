import boto3
import moto
import pytest
from boto3utils import s3

from cirrus.lib2.eventdb import EventDB


@pytest.fixture
def boto3utils_s3():
    with moto.mock_s3():
        yield s3(boto3.session.Session(region_name="us-east-1"))


@pytest.fixture
def sqs():
    with moto.mock_sqs():
        yield boto3.client("sqs", region_name="us-east-1")


@pytest.fixture
def dynamo():
    with moto.mock_dynamodb():
        yield boto3.client("dynamodb", region_name="us-east-1")


@pytest.fixture
def statedb(dynamo, statedb_schema):
    dynamo.create_table(**statedb_schema)
    return statedb_schema["TableName"]


@pytest.fixture
def timestream_write_client():
    with moto.mock_timestreamwrite():
        yield boto3.client("timestream-write", region_name="us-east-1")


@pytest.fixture
def eventdb(timestream_write_client):
    timestream_write_client.create_database(DatabaseName="event-db-1")
    timestream_write_client.create_table(
        DatabaseName="event-db-1", TableName="event-table-1"
    )
    return EventDB("event-db-1|event-table-1")
