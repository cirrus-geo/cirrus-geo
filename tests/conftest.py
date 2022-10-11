import os
import shutil
import json

import pytest
import moto
import boto3

from cirrus.core.project import Project

from . import plugin_testing


@pytest.fixture(scope='session')
def fixtures(pytestconfig):
    return  pytestconfig.rootpath.joinpath('tests', 'fixtures')


@pytest.fixture(scope='module')
def project_testdir(pytestconfig):
    pdir = pytestconfig.rootpath.joinpath('tests', 'output')
    if pdir.is_dir():
        shutil.rmtree(pdir)
    pdir.mkdir()
    old_cwd = os.getcwd()
    os.chdir(pdir)
    yield pdir
    os.chdir(old_cwd)


@pytest.fixture
def project(project_testdir):
    return Project.resolve(strict=True)


@pytest.fixture(scope='session', autouse=True)
def test_plugin(fixtures):
    dist = fixtures.joinpath('plugin', 'cirrus_test_plugin-0.0.0.dist-info')
    plugin_testing.add_plugin_finder(dist)
    yield
    plugin_testing.remove_plugin_finder(dist)


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    os.environ['AWS_REGION'] = 'us-east-1'


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
    with moto.mock_dynamodb2():
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
def statedb(dynamo, fixtures):
    schema = json.loads(fixtures.joinpath('statedb-schema.json').read_text())
    table = dynamo.create_table(**schema)
    return schema['TableName']


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
