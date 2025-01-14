import os

import pytest


@pytest.fixture(autouse=True)
def workflow_event_topic(sns):
    return sns.create_topic(Name="app-cirrus-workflow-event")["TopicArn"]


@pytest.fixture(autouse=True)
def publish_topic(sns):
    return sns.create_topic(Name="app-cirrus-publish")["TopicArn"]


@pytest.fixture(autouse=True)
def _env(_environment, queue, publish_topic, eventdb, statedb, payloads):
    os.environ["CIRRUS_PROCESS_QUEUE_URL"] = queue["QueueUrl"]
    os.environ["CIRRUS_PUBLISH_TOPIC_ARN"] = publish_topic
    os.environ["CIRRUS_STATE_DB"] = statedb.table_name
    os.environ["CIRRUS_EVENT_DB_AND_TABLE"] = (
        f"{eventdb.event_db_name}|{eventdb.event_table_name}"
    )
    os.environ["CIRRUS_PAYLOAD_BUCKET"] = payloads
