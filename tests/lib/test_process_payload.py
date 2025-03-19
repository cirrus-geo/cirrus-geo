import copy
import json

from pathlib import Path

import pytest

from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.utils import build_item_sns_attributes, recursive_compare

fixtures = Path(__file__).parent.joinpath("fixtures")


def read_json_fixture(filename):
    with fixtures.joinpath(filename).open() as f:
        return json.load(f)


@pytest.fixture()
def base_payload():
    return read_json_fixture("test-payload.json")


@pytest.fixture()
def sqs_event():
    return read_json_fixture("sqs-event.json")


@pytest.fixture()
def chain_payload(base_payload):
    # need to convert process and add filter
    base_payload["process"] = base_payload["process"] * 2
    base_payload["process"][1]["chain_filter"] = (
        "@.id =~ 'fake*' & @.properties.gsd <= 0"
    )

    # then add "fake" items
    new_item_count = 3
    features = base_payload["features"]
    features[0]["properties"]["gsd"] = new_item_count
    for index in range(1, new_item_count + 1):
        feature = copy.deepcopy(features[0])
        feature["id"] = f"fake_id{index}"
        # we decrement the gsd value so our search will
        # return only the last feature per the a gsd of 0
        feature["properties"]["gsd"] = new_item_count - index
        features.append(feature)

    return base_payload


@pytest.fixture()
def chain_filter_payload(chain_payload):
    # should only have the last feature and second process def
    chain_filter_result = copy.deepcopy(chain_payload)
    chain_filter_result["features"] = [chain_payload["features"][-1]]
    chain_filter_result["process"].pop(0)
    del chain_filter_result["id"]
    return chain_filter_result


def test_open_payload(base_payload):
    payload = ProcessPayload(**base_payload)
    assert (
        payload["id"] == "sentinel-s2-l2a/workflow-cog-archive/S2B_17HQD_20201103_0_L2A"
    )


def test_update_payload(base_payload):
    del base_payload["id"]
    del base_payload["features"][0]["links"]
    payload = ProcessPayload(**base_payload, set_id_if_missing=True)
    assert (
        payload["id"] == "sentinel-s2-l2a/workflow-cog-archive/S2B_17HQD_20201103_0_L2A"
    )


def test_from_event(sqs_event):
    payload = ProcessPayload.from_event(sqs_event, set_id_if_missing=True)
    assert len(payload["features"]) == 1
    assert (
        payload["id"]
        == "sentinel-s2-l2a-aws/workflow-publish-sentinel/tiles-17-H-QD-2020-11-3-0"
    )


def test_next_payloads_no_list(base_payload):
    payloads = list(ProcessPayload.from_event(base_payload).next_payloads())
    assert len(payloads) == 0


def test_next_payloads_list_of_one(base_payload):
    payloads = list(ProcessPayload.from_event(base_payload).next_payloads())
    assert len(payloads) == 0


def test_next_payloads_list_of_four(base_payload):
    length = 4
    list_payload = copy.deepcopy(base_payload)
    list_payload["process"] = base_payload["process"] * length

    # We should now have something like this:
    #
    # payload
    #   process:
    #     - wf1
    #     - wf2
    #     - wf3
    #     - wf4
    payloads = list(ProcessPayload.from_event(list_payload).next_payloads())

    # When we call next_payloads, we find one next payload (wf2)
    # with two to follow. So the length of the list returned should be
    # one, a process payload with a process array of length 3.
    assert len(payloads) == 1
    assert payloads[0]["process"] == base_payload["process"] * (length - 1)


def test_next_payloads_list_of_four_fork(base_payload):
    length = 3
    list_payload = copy.deepcopy(base_payload)
    list_payload["process"] = base_payload["process"] * length
    list_payload["process"][1] = base_payload["process"] * 2

    # We should now have something like this:
    #
    # payload
    #   process:
    #     - wf1
    #     - [ wf2a, wf2b]  # noqa: ERA001
    #     - wf3
    #     - wf4
    payloads = list(ProcessPayload.from_event(list_payload).next_payloads())

    # When we call next_payloads, we find two next payloads
    # (wf2a and wf2b), each with two to follow. So the length of
    # the list returned should be two, each a process payload
    # with a process array of length 3.
    assert len(payloads) == 2
    assert payloads[0]["process"] == base_payload["process"] * (length - 1)
    assert payloads[1]["process"] == base_payload["process"] * (length - 1)


def test_next_payloads_chain_filter(chain_payload, chain_filter_payload):
    payloads = list(
        ProcessPayload(chain_payload, set_id_if_missing=True).next_payloads(),
    )
    assert len(payloads) == 1
    assert not recursive_compare(payloads[0], chain_payload)
    assert recursive_compare(payloads[0], chain_filter_payload)


def test_payload_no_process(base_payload):
    del base_payload["process"]
    expected = "ProcessPayload must have a `process` array of process definintions"
    with pytest.raises(ValueError, match=expected):
        ProcessPayload.from_event(base_payload)


def test_payload_empty_process_array(base_payload):
    base_payload["process"] = []
    expected = (
        "ProcessPayload `process` must be an array "
        "with at least one process definition"
    )
    with pytest.raises(TypeError, match=expected):
        ProcessPayload.from_event(base_payload)


def test_payload_process_not_an_array(base_payload):
    base_payload["process"] = base_payload["process"][0]
    expected = (
        "ProcessPayload `process` must be an array "
        "with at least one process definition"
    )
    with pytest.raises(TypeError, match=expected):
        ProcessPayload.from_event(base_payload)


def test_items_to_sns_messages(base_payload):
    # SNSMessage instances do not implement the equality dunder method; instead,
    # compare the rendered message contents.
    messages = [
        message.render()
        for message in ProcessPayload.from_event(base_payload).items_to_sns_messages()
    ]
    expected = [
        {
            "Message": json.dumps(base_payload["features"][0]),
            "MessageAttributes": build_item_sns_attributes(base_payload["features"][0]),
        },
    ]
    assert messages == expected


def test_fail_and_raise(base_payload):
    payload = ProcessPayload(**base_payload)
    with pytest.raises(Exception):
        payload._fail_and_raise()
