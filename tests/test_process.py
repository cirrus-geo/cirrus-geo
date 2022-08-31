import os

import pytest

from cirrus.test import run_function


@pytest.fixture
def process_env(queue, statedb, workflow, payloads):
    workflow_prefix = workflow['stateMachineArn'].rsplit(':', 1)[0]
    os.environ['CIRRUS_PROCESS_QUEUE'] = queue['QueueUrl']
    os.environ['CIRRUS_STATE_DB'] = statedb
    os.environ['CIRRUS_BASE_WORKFLOW_ARN'] = workflow_prefix
    os.environ['CIRRUS_PAYLOAD_BUCKET'] = payloads


def test_process_empty_event(process_env):
    with pytest.raises(Exception):
        run_function('process', {})
