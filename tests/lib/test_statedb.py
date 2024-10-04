import os

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from cirrus.lib.enums import StateEnum
from cirrus.lib.statedb import StateDB

os.environ["CIRRUS_PAYLOAD_BUCKET"] = "test"

# fixtures
test_dbitem: dict[str, Any] = {
    "collections_workflow": "col1_wf1",
    "itemids": "item1/item2",
    "state_updated": f"QUEUED_{datetime.now(tz=UTC)}",
    "created": datetime.now(tz=UTC),
    "updated": datetime.now(tz=UTC),
}
test_item: dict[str, Any] = {
    "id": "col1/workflow-wf1/item1/item2",
    "process": {"upload_options": {"collections": {"output-collection": ".*"}}},
}


# use a low limit to force paging
RECORD_LIMIT = 10

STATES = list(StateEnum._member_names_)


def create_items_bulk(item_count, fns, **kwargs):
    if callable(fns):
        fns = [fns]
    for index in range(item_count):
        for fn in fns:
            newitem = deepcopy(test_item)
            fn(f'{newitem["id"]}{index}', **kwargs)


TESTKEY = {"collections_workflow": "col1_wf1", "itemids": "item1/item2"}


def test_payload_id_to_key():
    key = StateDB.payload_id_to_key(test_item["id"])
    assert key["collections_workflow"] == "col1_wf1"
    assert key["itemids"] == "item1/item2"


def test_key_to_payload_id():
    payload_id = StateDB.key_to_payload_id(TESTKEY)
    assert payload_id == test_item["id"]


def test_payload_key_to_url():
    url = StateDB.payload_key_to_url(TESTKEY)
    assert f"{test_item['id']}/input.json" in url


def test_dbitem_to_item():
    item = StateDB.dbitem_to_item(test_dbitem)
    assert item["payload_id"] == test_item["id"]
    assert item["workflow"] == "wf1"
    assert item["state"] == "QUEUED"


def test_since_to_timedelta():
    td = StateDB.since_to_timedelta("1d")
    assert td.days == 1
    td = StateDB.since_to_timedelta("1h")
    assert td.seconds == 3600
    td = StateDB.since_to_timedelta("10m")
    assert td.seconds == 600


@pytest.fixture()
def state_table(statedb: StateDB):
    statedb.limit = RECORD_LIMIT
    statedb.claim_processing(
        f'{test_item["id"]}_claimed',
        execution_arn="arn::notexecuted",
    )
    statedb.claim_processing(
        f'{test_item["id"]}_processing',
        execution_arn="arn::test",
    )
    statedb.set_processing(
        f'{test_item["id"]}_processing',
        execution_arn="arn::test",
    )
    statedb.set_completed(
        f'{test_item["id"]}_completed',
        outputs=["item1", "item2"],
    )
    statedb.set_failed(
        f'{test_item["id"]}_failed',
        "failed",
    )
    statedb.set_invalid(
        f'{test_item["id"]}_invalid',
        "invalid",
    )
    statedb.set_aborted(
        f'{test_item["id"]}_aborted',
    )
    yield statedb
    statedb.delete()


def test_get_items(state_table: StateDB):
    items = state_table.get_items(
        test_dbitem["collections_workflow"],
        state="PROCESSING",
        since="1h",
    )
    assert len(items) == 1


def test_get_items_bulk(state_table: StateDB):
    _count = 25
    create_items_bulk(
        _count,
        [state_table.claim_processing, state_table.set_processing],
        execution_arn="arn::test",
    )
    items = state_table.get_items(
        test_dbitem["collections_workflow"],
        state="PROCESSING",
        since="1h",
    )
    assert len(items) == _count + 1


def test_get_items_limit_1(state_table: StateDB):
    items = state_table.get_items(
        test_dbitem["collections_workflow"],
        state="PROCESSING",
        since="1h",
        limit=1,
    )
    assert len(items) == 1


def test_get_items_limit_1_bulk(state_table: StateDB):
    create_items_bulk(
        20,
        [state_table.claim_processing, state_table.set_processing],
        execution_arn="arn::test",
    )
    items = state_table.get_items(
        test_dbitem["collections_workflow"],
        state="PROCESSING",
        since="1h",
        limit=1,
    )
    assert len(items) == 1


def test_get_items_error(state_table: StateDB):
    items = state_table.get_items(
        test_dbitem["collections_workflow"],
        error_begins_with="failed",
    )
    assert len(items) == 1


def test_get_items_error_with_state(state_table: StateDB):
    items = state_table.get_items(
        test_dbitem["collections_workflow"],
        state="FAILED",
        error_begins_with="failed",
    )
    assert len(items) == 1


def test_get_items_error_no_items(state_table: StateDB):
    items = state_table.get_items(
        test_dbitem["collections_workflow"],
        error_begins_with="nonsense-prefix",
    )
    assert len(items) == 0


def test_get_dbitem(state_table: StateDB):
    dbitem = state_table.get_dbitem(test_item["id"] + "_processing")
    assert dbitem["itemids"] == test_dbitem["itemids"] + "_processing"
    assert dbitem["collections_workflow"] == test_dbitem["collections_workflow"]
    assert dbitem["state_updated"].startswith("PROCESSING")


def test_get_dbitem_noitem(state_table: StateDB):
    dbitem = state_table.get_dbitem("no-collection/workflow-none/fake-id")
    assert dbitem is None


def test_get_dbitems(state_table: StateDB):
    count = 5
    create_items_bulk(
        count,
        [state_table.claim_processing, state_table.set_processing],
        execution_arn="arn::test",
    )
    ids = [test_item["id"] + str(i) for i in range(count)]
    dbitems = state_table.get_dbitems(ids)
    assert len(dbitems) == len(ids)
    for dbitem in dbitems:
        assert state_table.key_to_payload_id(dbitem) in ids


def test_get_dbitems_duplicates(state_table: StateDB):
    count = 5
    create_items_bulk(
        count,
        [state_table.claim_processing, state_table.set_processing],
        execution_arn="arn::test",
    )
    ids = [test_item["id"] + str(i) for i in range(count)]
    ids.append(ids[0])
    dbitems = state_table.get_dbitems(ids)
    for dbitem in dbitems:
        assert state_table.key_to_payload_id(dbitem) in ids


def test_get_dbitems_noitems(state_table: StateDB):
    dbitems = state_table.get_dbitems(["no-collection/workflow-none/fake-id"])
    assert len(dbitems) == 0


def test_get_state(state_table: StateDB):
    for s in STATES:
        state = state_table.get_state(test_item["id"] + f"_{s.lower()}")
        assert state == s
    state = state_table.get_state(test_item["id"] + "nosuchitem")
    assert state is None


def test_get_states(state_table: StateDB):
    ids = [test_item["id"] + f"_{s.lower()}" for s in STATES]
    states = state_table.get_states(ids)
    assert len(ids) == len(states)
    for i, id in enumerate(ids):
        assert states[id] == STATES[i]


def test_get_counts(state_table: StateDB):
    _count = 3
    create_items_bulk(
        _count,
        [state_table.claim_processing, state_table.set_processing],
        execution_arn="arn::test",
    )
    count = state_table.get_counts(test_dbitem["collections_workflow"])
    assert count == _count + len(STATES)
    for s in STATES:
        count = state_table.get_counts(test_dbitem["collections_workflow"], state=s)
        if s == "PROCESSING":
            assert count == _count + 1
        else:
            assert count == 1
    count = state_table.get_counts(test_dbitem["collections_workflow"], since="1h")


def test_get_counts_error(state_table: StateDB):
    _count = 25
    create_items_bulk(_count, state_table.set_failed, msg="failed")
    count = state_table.get_counts(
        test_dbitem["collections_workflow"],
        error_begins_with="fail",
    )
    assert count == _count + 1


def test_get_counts_state(state_table: StateDB):
    _count = 25
    create_items_bulk(_count, state_table.set_failed, msg="failed")
    count = state_table.get_counts(
        test_dbitem["collections_workflow"],
        state="FAILED",
    )
    assert count == _count + 1


def test_get_counts_state_limit(state_table: StateDB):
    _count = 25
    create_items_bulk(_count, state_table.set_failed, msg="failed")
    count = state_table.get_counts(
        test_dbitem["collections_workflow"],
        state="FAILED",
        limit=15,
    )
    assert count == "15+"


def test_get_counts_since_limit_under(state_table: StateDB):
    _count = 20
    create_items_bulk(_count, state_table.set_failed, msg="failed")
    count = state_table.get_counts(
        test_dbitem["collections_workflow"],
        since="1h",
        limit=30,
    )
    assert count == _count + len(STATES)


def test_get_counts_since(state_table: StateDB):
    _count = 25
    create_items_bulk(_count, state_table.set_failed, msg="failed")
    count = state_table.get_counts(
        test_dbitem["collections_workflow"],
        since="1h",
    )
    assert count == _count + len(STATES)


def test_get_counts_since_state(state_table: StateDB):
    _count = 25
    create_items_bulk(_count, state_table.set_failed, msg="failed")
    count = state_table.get_counts(
        test_dbitem["collections_workflow"],
        since="1h",
        state="FAILED",
    )
    assert count == _count + 1


def test_set_processing(state_table: StateDB):
    state_table.set_processing(test_item["id"], execution_arn="arn::test1")
    dbitem = state_table.get_dbitem(test_item["id"])
    assert StateDB.key_to_payload_id(dbitem) == test_item["id"]
    assert dbitem["executions"] == ["arn::test1"]


def test_second_execution(state_table: StateDB):
    # check that processing adds new execution to list
    state_table.set_processing(test_item["id"], execution_arn="arn::test1")
    state_table.set_processing(test_item["id"], execution_arn="arn::test2")
    dbitem = state_table.get_dbitem(test_item["id"])
    assert len(dbitem["executions"]) == 2
    assert dbitem["executions"][-1] == "arn::test2"


def test_set_outputs_(state_table: StateDB):
    state_table.set_outputs(test_item["id"], outputs=["output-item"])
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["outputs"][0] == "output-item"


def test_set_outputs_completed(state_table: StateDB):
    state_table.set_completed(test_item["id"], outputs=["output-item"])
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["outputs"][0] == "output-item"


def test_set_completed(state_table: StateDB):
    state_table.set_completed(test_item["id"])
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["state_updated"].startswith("COMPLETED")


def test_set_failed(state_table: StateDB):
    state_table.set_failed(test_item["id"], msg="test failure")
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["state_updated"].startswith("FAILED")
    assert dbitem["last_error"] == "test failure"


def test_set_completed_with_outputs(state_table: StateDB):
    state_table.set_completed(test_item["id"], outputs=["output-item2"])
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["state_updated"].startswith("COMPLETED")
    assert dbitem["outputs"][0] == "output-item2"


def test_set_invalid(state_table: StateDB):
    state_table.set_invalid(test_item["id"], msg="test failure")
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["state_updated"].startswith("INVALID")
    assert dbitem["last_error"] == "test failure"


def test_set_aborted(state_table: StateDB):
    state_table.set_aborted(test_item["id"])
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["state_updated"].startswith("ABORTED")


def test_delete_item(state_table: StateDB):
    state_table.delete_item(test_item["id"])
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem is None


def test_claim_processing(state_table: StateDB):
    state_table.claim_processing(test_item["id"])
    dbitem = state_table.get_dbitem(test_item["id"])
    assert dbitem["state_updated"].startswith("PROCESSING")
