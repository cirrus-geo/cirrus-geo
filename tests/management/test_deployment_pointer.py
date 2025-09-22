import boto3
import pytest

from cirrus.management.deployment_pointer import (
    REQUIRED_VARS,
    DeploymentPointer,
    ParamStoreDeployment,
    Pointer,
)
from cirrus.management.exceptions import MissingParameterError
from tests.management.test_manage import MOCK_DEPLOYMENT_NAME

VALID_ENV = {
    "CIRRUS_PAYLOAD_BUCKET": "bucket",
    "CIRRUS_BASE_WORKFLOW_ARN": "workflow-arn",
    "CIRRUS_PROCESS_QUEUE_URL": "queue-url",
    "CIRRUS_STATE_DB": "state-db",
    "CIRRUS_EVENT_DB_AND_TABLE": "db|tb",
    "CIRRUS_PREFIX": "prefix",
    "CIRRUS_CLI_IAM_ARN": "arn:aws:iam::000000000000:role/test-role-arn",
}


def test_fetch(ssm, put_parameters):
    # test the actual fetch part in ParamStoreDeployment
    key = "/deployment/lion/"
    session = boto3.Session()
    dep = ParamStoreDeployment(key)
    env = dep.fetch(session)
    assert env.keys() == VALID_ENV.keys()


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        pytest.param(
            VALID_ENV,
            VALID_ENV,
            id="valid env passes",
        ),
        pytest.param(
            {},
            MissingParameterError(
                "CIRRUS_BASE_WORKFLOW_ARN, CIRRUS_PAYLOAD_BUCKET,  CIRRUS_STATE_DB, CIRRUS_PREFIX, CIRRUS_PROCESS_QUEUE_URL",
            ),
            id="missing vars raises error",
        ),
    ],
)
def test_validate_vars(environment, expected):
    dp = DeploymentPointer(MOCK_DEPLOYMENT_NAME, Pointer("parameter_store", "val"))
    if isinstance(expected, Exception):
        with pytest.raises(MissingParameterError) as e:
            actual = dp.validate_vars(environment)
        for env_var in REQUIRED_VARS:
            assert env_var in e.value.args[0]
    else:
        actual = dp.validate_vars(environment)
        assert actual == expected
