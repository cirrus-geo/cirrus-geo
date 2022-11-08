import uuid

import pytest

from cirrus.lib2.eventdb import StateEnum


@pytest.fixture
def event_kwargs():
    return {
        "key": {"collections_workflow": "sentinel2_cogification", "itemids": "xxxaaaa"},
        "state": StateEnum.PROCESSING,
        "event_time": "2011-11-04T00:05:23+00:00",
        "execution_arn": f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{str(uuid.uuid4())}",
    }


def test_writing_record(eventdb, event_kwargs):
    response = eventdb.write_timeseries_record(**event_kwargs)
    assert response.get("RecordsIngested", {}).get("Total") == 1


def test_writing_record_no_arn(eventdb, event_kwargs):
    event_kwargs["execution_arn"] = None
    response = eventdb.write_timeseries_record(**event_kwargs)
    assert response.get("RecordsIngested", {}).get("Total") == 1


def test_writing_record_no_collections_workflow(eventdb, event_kwargs):
    event_kwargs["key"].pop("collections_workflow")
    assert not eventdb.write_timeseries_record(**event_kwargs)


def test_writing_record_no_itemids(eventdb, event_kwargs):
    event_kwargs["key"].pop("itemids")
    assert not eventdb.write_timeseries_record(**event_kwargs)


def test_writing_record_invalid_datetime(eventdb, event_kwargs):
    event_kwargs["event_time"] = "xxxxxx"
    assert not eventdb.write_timeseries_record(**event_kwargs)
