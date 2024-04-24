import os

import pytest

from cirrus.lib2.events import WorkflowEventManager


@pytest.mark.parametrize(
    ("event_type", "payload_id", "extra_message", "error_message"),
    (
        ("blah", None, None, r"Must specify a payload_id"),
        (
            "blah",
            "some_id",
            {"payload_id": None},
            r"extra_message parameters must not.*",
        ),
    ),
)
def test_anounce_errors(
    event_type,
    payload_id,
    extra_message,
    error_message,
    statedb,
):
    os.environ["CIRRUS_STATE_DB"] = statedb.table_name
    os.environ["CIRRUS_WORKFLOW_EVENT_TOPIC_ARN"] = "bleh"
    wfem = WorkflowEventManager()
    with pytest.raises(ValueError, match=error_message):
        wfem.announce(event_type, payload_id, extra_message=extra_message)
