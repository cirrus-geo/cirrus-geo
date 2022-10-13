import os
import json

import pytest

from pathlib import Path


def set_fake_creds():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    os.environ['AWS_REGION'] = 'us-east-1'


set_fake_creds()


@pytest.fixture(autouse=True)
def aws_credentials():
    set_fake_creds()


@pytest.fixture(scope='session')
def fixtures():
    return Path(__file__).parent.joinpath('fixtures')


@pytest.fixture(scope='session')
def statedb_schema(fixtures):
    return json.loads(fixtures.joinpath('statedb-schema.json').read_text())
