import boto3
import moto
import pytest

from boto3utils import s3


@pytest.fixture
def boto3utils_s3():
    with moto.mock_aws():
        yield s3(boto3.session.Session(region_name="us-east-1"))


@pytest.fixture
def sqs():
    with moto.mock_aws():
        yield boto3.client("sqs", region_name="us-east-1")


@pytest.fixture
def sns():
    with moto.mock_aws():
        yield boto3.client("sns", region_name="us-east-1")


@pytest.fixture
def dynamo():
    with moto.mock_aws():
        yield boto3.client("dynamodb", region_name="us-east-1")
