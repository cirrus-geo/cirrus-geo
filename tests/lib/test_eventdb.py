import uuid
from copy import deepcopy

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

def test_writing_record(eventdb, timestream_write_client):
    valid_kwargs = {
        "key": {"collections_workflow": "sentinel2_cogification", "itemids": "xxxaaaa"},
        "state": StateEnum.PROCESSING,
        "event_time": "2011-11-04T00:05:23+00:00",
        "execution_arn": f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{str(uuid.uuid4())}",
    }

def test_writing_record(eventdb, event_kwargs):
    response = eventdb.write_timeseries_record(**event_kwargs)
    assert response.get("RecordsIngested", {}).get("Total") == 1


def test_writing_record_no_collections_workflow(eventdb, event_kwargs):
    event_kwargs["key"].pop("collections_workflow")
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**event_kwargs)


def test_writing_record_no_itemids(eventdb, event_kwargs):
    event_kwargs["key"].pop("itemids")
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**event_kwargs)

def test_writing_record_invalid_datetime(eventdb, event_kwargs):
    event_kwargs["event_time"] = "xxxxxx"
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**event_kwargs)

    response = eventdb.write_timeseries_record(**valid_kwargs)
    assert response.get("RecordsIngested", {}).get("Total") == 1

    kwargs = deepcopy(valid_kwargs)
    kwargs["execution_arn"] = None
    response = eventdb.write_timeseries_record(**kwargs)
    assert response.get("RecordsIngested", {}).get("Total") == 1

    # missing collections_workflow
    kwargs = deepcopy(valid_kwargs)
    kwargs["key"].pop("collections_workflow")
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**kwargs)

    # missing itemids
    kwargs = deepcopy(valid_kwargs)
    kwargs["key"].pop("itemids")
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**kwargs)

    # invalid datetime
    kwargs = deepcopy(valid_kwargs)
    kwargs["event_time"] = "xxxxxx"
    with pytest.raises(ValueError):
        eventdb.write_timeseries_record(**kwargs)

