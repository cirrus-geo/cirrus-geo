import uuid

import boto3
import moto
import pytest

from cirrus.lib2.eventdb import EventDB, StateEnum


@pytest.fixture
def timestream_write_client():
    with moto.mock_timestreamwrite():
        yield boto3.client("timestream-write", region_name="us-east-1")


@pytest.fixture
def eventdb(timestream_write_client):
    timestream_write_client.create_database(DatabaseName="event-db-1")
    timestream_write_client.create_table(
        DatabaseName="event-db-1", TableName="event-table-1"
    )
    return EventDB("event-db-1|event-table-1")


def test_writing_record(eventdb, timestream_write_client):
    response = eventdb.write_timeseries_record(
        key={"collections_workflow": "sentinel2_cogification", "itemids": "xxxaaaa"},
        state=StateEnum.PROCESSING,
        event_time="2011-11-04T00:05:23+00:00",
        execution_arn=f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{str(uuid.uuid4())}",
    )
    assert response.get("RecordsIngested", {}).get("Total") == 1

    # missing collections_workflow
    assert not eventdb.write_timeseries_record(
        key={
            "______collections_workflow": "sentinel2_cogification",
            "itemids": "xxxaaaa",
        },
        state=StateEnum.PROCESSING,
        event_time="2011-11-04T00:05:23+00:00",
        execution_arn=f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{str(uuid.uuid4())}",
    )

    # missing itemids
    assert not eventdb.write_timeseries_record(
        key={
            "collections_workflow": "sentinel2_cogification",
            "____itemids": "xxxaaaa",
        },
        state=StateEnum.PROCESSING,
        event_time="2011-11-04T00:05:23+00:00",
        execution_arn=f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{str(uuid.uuid4())}",
    )

    # Z datetime isn't allowed
    with pytest.raises(Exception):
        eventdb.write_timeseries_record(
            key={
                "collections_workflow": "sentinel2_cogification",
                "itemids": "xxxaaaa",
            },
            state=StateEnum.PROCESSING,
            event_time="2011-11-04T00:05:23Z",
            execution_arn=f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{str(uuid.uuid4())}",
        )
