import os
import uuid

import pytest

from cirrus.lib2.eventdb import EventDB, StateEnum


@pytest.fixture
def event_kwargs():
    return {
        "payload_id": "sentinel2/workflow-cogification/xxxaaaa",
        "state": StateEnum.PROCESSING,
        "event_time": "2011-11-04T00:05:23+00:00",
        "execution_arn": f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{str(uuid.uuid4())}",
    }


def test_writing_record(eventdb, event_kwargs):
    response = eventdb.write_timeseries_record(**event_kwargs)
    assert response.get("RecordsIngested", {}).get("Total") == 1


def test_writing_record_no_collections_workflow(eventdb, event_kwargs):
    event_kwargs["payload_id"] = event_kwargs["payload_id"].replace("sentinel2/", "")
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**event_kwargs)


def test_writing_record_no_itemids(eventdb, event_kwargs):
    event_kwargs["payload_id"] = event_kwargs["payload_id"].replace("/xxxaaaa", "")
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**event_kwargs)


def test_writing_record_invalid_datetime(eventdb, event_kwargs):
    event_kwargs["event_time"] = "xxxxxx"
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**event_kwargs)


def test_eventdb_with_invalid_init_string(event_kwargs):
    with pytest.raises(Exception):
        EventDB("asfasf")


def test_eventdb_without_configuration(event_kwargs):
    # ensure timeseries disabled
    os.environ.pop("CIRRUS_EVENT_DB_AND_TABLE", None)

    eventdb = EventDB(None)
    assert not eventdb.enabled()
    assert eventdb.write_timeseries_record(**event_kwargs) is None
    assert eventdb.query_hour(1, 2) is None
    assert eventdb.query_by_bin_and_duration("", "") is None
