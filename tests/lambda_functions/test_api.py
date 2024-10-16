import json

import pytest

from cirrus.lambda_functions import api
from cirrus.lib.errors import EventsDisabledError


def test_empty_event():
    with pytest.raises(Exception):
        api.lambda_handler({}, {})


@pytest.mark.usefixtures("_env")
def test_daily_results(fixtures):
    eventdb_daily_input = json.loads(
        fixtures.joinpath("eventdb-daily-input.json").read_text(),
    )
    expected_output = json.loads(
        fixtures.joinpath("eventdb-daily-expected.json").read_text(),
    )
    actual_output = api.daily(eventdb_daily_input)
    assert actual_output == expected_output


@pytest.mark.usefixtures("_env")
def test_hourly_results(fixtures):
    eventdb_hourly_input = json.loads(
        fixtures.joinpath("eventdb-hourly-input.json").read_text(),
    )
    expected_output = json.loads(
        fixtures.joinpath("eventdb-hourly-expected.json").read_text(),
    )
    actual_output = api.hourly(eventdb_hourly_input)
    assert actual_output == expected_output


class MockEventDB:
    def __init__(self, fixtures, enabled: bool = True):
        self.fixtures = fixtures
        self._enabled = enabled

    def enabled(self):
        return self._enabled

    def query_by_bin_and_duration(self, x, y):
        if not self.enabled():
            raise EventsDisabledError

        if x == "1d":
            return json.loads(
                self.fixtures.joinpath("eventdb-daily-input.json").read_text(),
            )
        if x == "1h":
            return json.loads(
                self.fixtures.joinpath("eventdb-hourly-input.json").read_text(),
            )
        raise Exception(f"bin size {x} unexpected")

    def query_hour(self, x, y):
        if not self.enabled():
            raise EventsDisabledError

        return {"Rows": []}


def test_api_stats_output(fixtures):
    actual_result = api.get_stats(MockEventDB(fixtures))
    expected_result = {
        "state_transitions": {
            "daily": json.loads(
                fixtures.joinpath("eventdb-daily-expected.json").read_text(),
            ),
            "hourly": json.loads(
                fixtures.joinpath("eventdb-hourly-expected.json").read_text(),
            ),
            "hourly_rolling": [],
        },
    }
    assert actual_result == expected_result


def test_api_stats_output_when_not_enabled(fixtures):
    assert api.get_stats(MockEventDB(fixtures, enabled=False)) is None


def test_api_collection_summary(statedb):
    itemid = "test-collection/workflow-test-workflow/badbeefa11da7"
    statedb.limit = 10
    statedb.claim_processing(
        f"{itemid}_claimed",
        execution_arn="arn::uuid5",
    )
    statedb.claim_processing(
        f"{itemid}_processing",
        execution_arn="arn::uuid5",
    )
    statedb.set_processing(
        f"{itemid}_processing",
        execution_arn="arn::uuid5",
    )
    statedb.set_completed(
        f"{itemid}_completed",
        outputs=["item1", "item2"],
    )
    statedb.set_failed(
        f"{itemid}_failed",
        "failed",
    )
    statedb.set_failed(
        f"{itemid}_failed2",
        "failed2",
    )
    statedb.set_invalid(
        f"{itemid}_invalid",
        "invalid",
    )
    statedb.set_aborted(
        f"{itemid}_aborted",
    )
    result = api.summary(
        "test-collection_test-workflow",
        "1d",
        10,
        statedb=statedb,
    )
    expected = {
        "collections": "test-collection",
        "workflow": "test-workflow",
        "counts": {
            "PROCESSING": 1,
            "CLAIMED": 1,
            "COMPLETED": 1,
            "FAILED": 2,
            "INVALID": 1,
            "ABORTED": 1,
        },
    }
    assert result == expected
