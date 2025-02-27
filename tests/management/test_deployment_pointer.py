import boto3

from cirrus.management.deployment_pointer import DeploymentPointer

from tests.conftest import MOCK_REGION

DEPLOYMENT_NAME = "lion"
LION_DEPLOYMENT = DeploymentPointer(
    "/cirrus/deployments/",
    "lion",
    {
        "CIRRUS_BASE_WORKFLOW_ARN": "arn:aws:states:us-east-1:00000000:stateMachine:fd-lion-dev-cirrus-",
        "CIRRUS_DATA_BUCKET": "filmdrop-lion-us-east-1-random-data-bucket-name",
        "CIRRUS_EVENT_DB_AND_TABLE": "fd-lion-dev-cirrus-nane-db|fd-lion-dev-cirrus-random-table",
        "CIRRUS_LOG_LEVEL": "DEBUG",
        "CIRRUS_PAYLOAD_BUCKET": "filmdrop-lion-us-east-1-cirrus-random-payload-bucket-000000",
        "CIRRUS_PREFIX": "fd-lion-dev-cirrus",
        "CIRRUS_PROCESS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/000000000/fd-lion-dev-cirrus-random-queue-name",
        "CIRRUS_STATE_DB": "fd-lion-dev-cirrus-random-state-db",
        "CIRRUS_WORKFLOW_EVENT_TOPIC_ARN": "arn:aws:sns:us-east-1:00000000000:fd-lion-dev-cirrus-random-workflow-name-here",
    },
)
SQUIRREL_DEPLOYMENT = DeploymentPointer(
    "/cirrus/deployments/",
    "squirrel/dev",
    {
        "CIRRUS_BASE_WORKFLOW_ARN": "arn:aws:states:us-east-1:00000000:stateMachine:fd-squirrel-dev-cirrus-",
        "CIRRUS_DATA_BUCKET": "filmdrop-squirrel-us-east-1-random-data-bucket-name",
        "CIRRUS_EVENT_DB_AND_TABLE": "fd-squirrel-dev-cirrus-nane-db|fd-squirrel-dev-cirrus-random-table",
        "CIRRUS_LOG_LEVEL": "DEBUG",
        "CIRRUS_PAYLOAD_BUCKET": "filmdrop-squirrel-us-east-1-cirrus-random-payload-bucket-000000",
        "CIRRUS_PREFIX": "fd-squirrel-dev-cirrus",
        "CIRRUS_PROCESS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/000000000/fd-squirrel-dev-cirrus-random-queue-name",
        "CIRRUS_STATE_DB": "fd-squirrel-dev-cirrus-random-state-db",
        "CIRRUS_WORKFLOW_EVENT_TOPIC_ARN": "arn:aws:sns:us-east-1:00000000000:fd-squirrel-dev-cirrus-random-workflow-name-here",
    },
)


def test_parse_deployments(parameter_store_response):
    actual = DeploymentPointer.parse_deployments(
        parameter_store_response,
        "/cirrus/deployments/",
    )
    expected = [
        LION_DEPLOYMENT,
    ]
    assert actual == expected


def test_get_deployments(put_parameters):
    deployments = DeploymentPointer._get_deployments(
        "/cirrus/deployments/",
        region=MOCK_REGION,
        session=boto3.Session(),
    )
    expected = [
        LION_DEPLOYMENT,
        SQUIRREL_DEPLOYMENT,
    ]
    assert deployments == expected


def test_get_deployment_by_name(put_parameters):
    deployment = DeploymentPointer.get_deployment_by_name(
        "lion",
        "/cirrus/deployments/",
        MOCK_REGION,
        boto3.Session(),
    )
    assert deployment == LION_DEPLOYMENT
