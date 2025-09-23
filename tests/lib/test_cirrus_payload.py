import json

from pathlib import Path

import pytest

from cirrus.lib.cirrus_payload import CirrusPayload

fixtures = Path(__file__).parent.joinpath("fixtures")


def read_json_fixture(filename):
    with fixtures.joinpath(filename).open() as f:
        return json.load(f)


@pytest.fixture
def base_payload():
    return read_json_fixture("test-payload.json")


@pytest.fixture
def sqs_event():
    return read_json_fixture("sqs-event.json")


def test_open_payload(base_payload):
    payload = CirrusPayload(base_payload)
    assert (
        payload["id"] == "sentinel-s2-l2a/workflow-cog-archive/S2B_17HQD_20201103_0_L2A"
    )


def test_update_payload(base_payload):
    del base_payload["id"]
    del base_payload["features"][0]["links"]
    payload = CirrusPayload(base_payload, set_id_if_missing=True)
    assert (
        payload["id"] == "sentinel-s2-l2a/workflow-cog-archive/S2B_17HQD_20201103_0_L2A"
    )


def test_from_event(sqs_event):
    payload = CirrusPayload.from_event(sqs_event, set_id_if_missing=True)
    assert len(payload["features"]) == 1
    assert (
        payload["id"]
        == "sentinel-s2-l2a-aws/workflow-publish-sentinel/tiles-17-H-QD-2020-11-3-0"
    )


def test_payload_no_process(base_payload):
    del base_payload["process"]
    expected = "Payload must contain a 'process' array of process definitions"
    with pytest.raises(ValueError, match=expected):
        CirrusPayload.from_event(base_payload).validate()


def test_payload_empty_process_array(base_payload):
    base_payload["process"] = []
    expected = (
        "Payload 'process' field must be an array with at least one process definition"
    )
    with pytest.raises(TypeError, match=expected):
        CirrusPayload.from_event(base_payload).validate()


def test_payload_process_not_an_array(base_payload):
    base_payload["process"] = base_payload["process"][0]
    expected = (
        "Payload 'process' field must be an array with at least one process definition"
    )
    with pytest.raises(TypeError, match=expected):
        CirrusPayload.from_event(base_payload).validate()
