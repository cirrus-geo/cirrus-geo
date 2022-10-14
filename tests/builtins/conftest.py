import json

import pytest
import moto
import boto3


@pytest.fixture
def s3(aws_credentials):
    with moto.mock_s3():
        yield boto3.client('s3', region_name='us-east-1')


@pytest.fixture
def sqs(aws_credentials):
    with moto.mock_sqs():
        yield boto3.client('sqs', region_name='us-east-1')


@pytest.fixture
def dynamo(aws_credentials):
    with moto.mock_dynamodb():
        yield boto3.client('dynamodb', region_name='us-east-1')


@pytest.fixture
def stepfunctions(aws_credentials):
    with moto.mock_stepfunctions():
        yield boto3.client("stepfunctions", region_name='us-east-1')


@pytest.fixture
def iam(aws_credentials):
    with moto.mock_iam():
        yield boto3.client("iam", region_name='us-east-1')


@pytest.fixture
def payloads(s3):
    name = 'payloads'
    s3.create_bucket(Bucket=name)
    return name


@pytest.fixture
def queue(sqs):
    q = sqs.create_queue(QueueName='test-queue')
    q['Arn'] = 'arn:aws:sqs:us-east-1:123456789012:test-queue'
    return q


@pytest.fixture
def statedb(dynamo, statedb_schema):
    dynamo.create_table(**statedb_schema)
    return statedb_schema['TableName']


@pytest.fixture
def workflow(stepfunctions, iam):
    defn = {
        'StartAt': 'FirstState',
        'States': {
            'FirstState': {
                'Type': 'Pass',
                'End': True,
            },
        },
    }
    role_policy = {
        'Version': '2012-10-17',
        'Statement': [{
            'Effect': 'Allow',
            'Principal': {
                'Service': 'states.us-east-1.amazonaws.com',
            },
            'Action': 'sts:AssumeRole',
        }],
    }
    role = iam.create_role(
        RoleName='test-step-function-role',
        AssumeRolePolicyDocument=json.dumps(role_policy),
    )['Role']
    return stepfunctions.create_state_machine(
        name='test-workflow1',
        definition=json.dumps(defn),
        roleArn=role['Arn'],
    )
