import moto
import boto3
import pytest

from boto3utils import s3


@pytest.fixture
def boto3utils_s3():
    with moto.mock_s3():
        yield s3(boto3.session.Session(region_name='us-east-1'))


@pytest.fixture
def sqs():
    with moto.mock_sqs():
        yield boto3.client('sqs', region_name='us-east-1')


@pytest.fixture
def dynamo():
    with moto.mock_dynamodb():
        yield boto3.client('dynamodb', region_name='us-east-1')


@pytest.fixture
def statedb(dynamo, statedb_schema):
    dynamo.create_table(**statedb_schema)
    return statedb_schema['TableName']
