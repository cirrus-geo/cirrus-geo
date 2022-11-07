import json

import pytest

import cirrus
from cirrus.test import run_function


def test_empty_event():
    with pytest.raises(Exception):
        run_function("api", {})


def test_daily_results(env, fixtures):
    eventdb_daily_input = json.loads(
        fixtures.joinpath("eventdb-daily-input.json").read_text()
    )
    expected_output = json.loads(
        fixtures.joinpath("eventdb-daily-expected.json").read_text()
    )
    actual_output = cirrus.builtins.functions.api.lambda_function.daily(
        eventdb_daily_input
    )
    assert actual_output == expected_output


def test_hourly_results(env, fixtures):
    eventdb_hourly_input = json.loads(
        fixtures.joinpath("eventdb-hourly-input.json").read_text()
    )
    expected_output = json.loads(
        fixtures.joinpath("eventdb-hourly-expected.json").read_text()
    )
    actual_output = cirrus.builtins.functions.api.lambda_function.hourly(
        eventdb_hourly_input
    )
    assert actual_output == expected_output


class MockEventDB:
    def __init__(self, fixtures):
        self.fixtures = fixtures

    def query_by_bin_and_duration(self, x, y):
        if x == "1d":
            return json.loads(
                self.fixtures.joinpath("eventdb-daily-input.json").read_text()
            )
        if x == "1h":
            return json.loads(
                self.fixtures.joinpath("eventdb-hourly-input.json").read_text()
            )
        raise Exception(f"bin size {x} unexpected")

    def query_hour(self, x, y):
        return {"Rows": []}


def test_api_stats_output(fixtures):
    actual_result = cirrus.builtins.functions.api.lambda_function.get_stats(
        MockEventDB(fixtures)
    )
    expected_result = {
        "state_transitions": {
            "daily": json.loads(
                fixtures.joinpath("eventdb-daily-expected.json").read_text()
            ),
            "hourly": json.loads(
                fixtures.joinpath("eventdb-hourly-expected.json").read_text()
            ),
            "hourly_rolling": [],
        }
    }
    assert actual_result == expected_result
