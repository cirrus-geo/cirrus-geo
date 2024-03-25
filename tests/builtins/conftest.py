import json
import os

import boto3
import moto
import pytest

from cirrus.core.components import Feeder, Function, Task


# we do these import shenannigans to ensure we pick up
# all builting lambda_handler.py files for test coverage
def import_builtin_lambdas(component_type):
    component_type.find()
    for component in component_type.values():
        if component.is_builtin and component.lambda_enabled:
            try:
                component.import_handler()
            except Exception:
                # we expect the imports will fail but that's okay
                # for what we are doing here
                pass


import_builtin_lambdas(Feeder)
import_builtin_lambdas(Function)
import_builtin_lambdas(Task)


@pytest.fixture
def s3(aws_credentials):
    with moto.mock_s3():
        yield boto3.client("s3", region_name="us-east-1")


@pytest.fixture
def sqs(aws_credentials):
    with moto.mock_sqs():
        yield boto3.client("sqs", region_name="us-east-1")


@pytest.fixture
def sns(aws_credentials):
    with moto.mock_sns():
        yield boto3.client("sns", region_name="us-east-1")


@pytest.fixture(autouse=True)
def workflow_event_topic(sns):
    return sns.create_topic(Name="app-cirrus-workflow-event")["TopicArn"]


@pytest.fixture
def stepfunctions(aws_credentials):
    with moto.mock_stepfunctions():
        yield boto3.client("stepfunctions", region_name="us-east-1")


@pytest.fixture
def iam(aws_credentials):
    with moto.mock_iam():
        yield boto3.client("iam", region_name="us-east-1")


@pytest.fixture
def payloads(s3):
    name = "payloads"
    s3.create_bucket(Bucket=name)
    return name


@pytest.fixture
def queue(sqs):
    q = sqs.create_queue(QueueName="test-queue")
    q["Arn"] = "arn:aws:sqs:us-east-1:123456789012:test-queue"
    return q


@pytest.fixture
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
            }
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


@pytest.fixture(autouse=True)
def env(queue, eventdb, statedb, payloads):
    os.environ["CIRRUS_PROCESS_QUEUE_URL"] = queue["QueueUrl"]
    os.environ["CIRRUS_STATE_DB"] = statedb.table_name
    os.environ[
        "CIRRUS_EVENT_DB_AND_TABLE"
    ] = f"{eventdb.event_db_name}|{eventdb.event_table_name}"
    os.environ["CIRRUS_PAYLOAD_BUCKET"] = payloads
