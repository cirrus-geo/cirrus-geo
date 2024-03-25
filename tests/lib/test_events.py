import os

import pytest

from cirrus.lib2.events import WorkflowEventManager


@pytest.mark.parametrize(
    ("event_type", "payload", "payload_id", "extra_message", "error_message"),
    (
        ("blah", None, None, None, r"must specify payload_id or payload"),
        (
            "blah",
            {"id": "banana"},
            "pancake",
            None,
            r".*must match, if both supplied\.",
        ),
        (
            "blah",
            None,
            "some_id",
            {"payload": None},
            r"extra_message parameters must not.*",
        ),
    ),
)
def test_anounce_errors(
    event_type,
    payload,
    payload_id,
    extra_message,
    error_message,
    statedb,
):
    os.environ["CIRRUS_STATE_DB"] = statedb.table_name
    os.environ["CIRRUS_WORKFLOW_EVENT_TOPIC_ARN"] = "bleh"
    wfem = WorkflowEventManager()
    with pytest.raises(ValueError, match=error_message):
        wfem.announce(event_type, payload, payload_id, extra_message)
