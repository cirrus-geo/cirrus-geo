import json

import pytest

from cirrus.lambda_functions import api
from cirrus.lib.enums import StateEnum
from cirrus.lib.errors import EventsDisabledError
from cirrus.lib.utils import parse_since


@pytest.fixture
def metric_data():
    return [
        {
            "events": {
                "PROCESSING": 0,
                "INVALID": 0,
                "ABORTED": 0,
                "CLAIMED": 0,
                "FAILED": 1,
                "SUCCEEDED": 1,
            },
            "period": "2025-09-29T17:48:00+00:00",
        },
    ]


def test_empty_event():
    with pytest.raises(Exception):
        api.lambda_handler({}, {})


def test_filter_for_dashboard(metric_data):
    filtered = api.filter_for_dashboard(metric_data, "hour")
    states = [
        {"state": state, "count": 0, "unique_count": 0}
        if state not in [StateEnum.FAILED, StateEnum.COMPLETED]
        else {"state": state, "count": 1, "unique_count": 1}
        for state in sorted(StateEnum._member_names_)
    ]

    assert sorted(filtered[0]["states"], key=lambda x: x["state"]) == states


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


class MockWorkflowMetricReader:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled

    def enabled(self):
        return self._enabled

    def query_by_bin_and_duration(self, x, y):
        if self.enabled():
            return [
                {
                    "period": "2025-09-29T17:48:00+00:00"
                    if x == "1h"
                    else "2025-09-29",
                    "events": {
                        "PROCESSING": 0,
                        "INVALID": 0,
                        "ABORTED": 0,
                        "CLAIMED": 0,
                        "FAILED": 1,
                        "SUCCEEDED": 1,
                    },
                },
            ]
        return []

    def query_hour(self, x, y):
        if self.enabled():
            return [
                {
                    "period": "2025-09-29T17:48:00+00:00",
                    "events": {
                        "PROCESSING": 0,
                        "INVALID": 0,
                        "ABORTED": 0,
                        "CLAIMED": 0,
                        "FAILED": 1,
                        "SUCCEEDED": 1,
                    },
                },
            ]
        return []


@pytest.mark.parametrize(
    ("eventdb_enabled", "metric_reader_enabled"),
    [(False, False), (True, False), (False, True)],
)
def test_api_stats_output(eventdb_enabled, metric_reader_enabled, fixtures):
    actual_result = api.get_stats(
        MockWorkflowMetricReader(enabled=metric_reader_enabled),
        MockEventDB(fixtures, enabled=eventdb_enabled),
    )
    eventdb_result = {
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
    states = [
        {"state": state, "count": 0, "unique_count": 0}
        if state not in [StateEnum.FAILED, StateEnum.COMPLETED]
        else {"state": state, "count": 1, "unique_count": 1}
        for state in sorted(StateEnum._member_names_)
    ]
    metric_reader_result = {
        "state_transitions": {
            "daily": [
                {
                    "interval": "day",
                    "period": "2025-09-29",
                    "states": states,
                },
            ],
            "hourly": [
                {
                    "interval": "hour",
                    "period": "2025-09-29T17:48:00+00:00",
                    "states": states,
                },
            ],
            "hourly_rolling": [
                {
                    "interval": "hour",
                    "period": "2025-09-29T17:48:00+00:00",
                    "states": states,
                },
                {
                    "interval": "hour",
                    "period": "2025-09-29T17:48:00+00:00",
                    "states": states,
                },
            ],
        },
    }
    if metric_reader_enabled:
        assert (
            sorted(
                actual_result["state_transitions"]["daily"][0]["states"],
                key=lambda x: x["state"],
            )
            == metric_reader_result["state_transitions"]["daily"][0]["states"]
        )
        assert (
            sorted(
                actual_result["state_transitions"]["hourly"][0]["states"],
                key=lambda x: x["state"],
            )
            == metric_reader_result["state_transitions"]["hourly"][0]["states"]
        )
        assert (
            sorted(
                actual_result["state_transitions"]["hourly_rolling"][0]["states"],
                key=lambda x: x["state"],
            )
            == metric_reader_result["state_transitions"]["hourly_rolling"][0]["states"]
        )
    elif eventdb_enabled:
        assert actual_result == eventdb_result
    else:
        assert actual_result is None


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
        parse_since("1d"),
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
