import json
import sys

from itertools import product

import pytest

from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.sns.models import sns_backends

from cirrus.lambda_functions.update_state import get_execution_error
from cirrus.lambda_functions.update_state import lambda_handler as update_state
from cirrus.lib.enums import SfnStatus
from cirrus.lib.events import WorkflowEvent

EVENT_PAYLOAD_ID = "test-collection/workflow-test-workflow/test-id"


@pytest.fixture
def event():
    return {
        "asctime": "2022-11-09T00:18:35+0000",
        "name": "lambda_function.update-state",
        "levelname": "DEBUG",
        "message": None,
        "version": "0",
        "id": "3d3281f9-5f46-5dc6-9bf7-fea13994432e",
        "detail-type": "Step Functions Execution Status Change",
        "source": "aws.states",
        "account": "123456789012",
        "time": "2022-11-09T00:17:18Z",
        "region": "us-east-1",
        "resources": [
            "arn:aws:states:us-east-1:123456789012:execution:test-workflow1:ef3ace61-4231-4488-9f55-17956ede0de7",
        ],
        "detail": {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-workflow1:ef3ace61-4231-4488-9f55-17956ede0de7",  # noqa: E501
            "stateMachineArn": "arn:aws:states:us-east-1:123456789012:stateMachine:test-workflow1",  # noqa: E501
            "name": "ef3ace61-4231-4488-9f55-17956ede0de7",
            "status": "SUCCEEDED",
            "startDate": 1667953034792,
            "stopDate": 1667953037547,
            "input": '{"id": "'
            + EVENT_PAYLOAD_ID
            + '", "type": "FeatureCollection", "features": [{"type": "Feature", "id": "test-id1", "collection": "test-collection-input1", "properties": {}, "assets": {}, "links": []}], "process": [{"workflow": "test-workflow1", "upload_options": {"path_template": "/${collection}/${year}/${month}/${day}/${id}", "collections": {"test-collection-output": ".*"}}, "tasks": {}}]}',  # noqa: E501
            "output": None,
            "inputDetails": {"included": True},
            "outputDetails": None,
        },
    }


def test_empty_event():
    with pytest.raises(Exception):
        update_state({}, {})


@pytest.mark.parametrize(
    ("wf_event_enabled", "sfn_state"),
    product((True, False), SfnStatus._member_names_),
)
def test_workflow_event_notification(
    event,
    statedb,
    workflow_event_topic,
    wf_event_enabled,
    sfn_state,
    monkeypatch,
):
    """This tests that workflow events are properly published (if `wf_event_enabled`),
    with the associated StepFunctions State.  It also verifies that the record is added
    to the `statedb`.  The content of that record is validated in separate
    `test_{StateEnum}` tests.

    N.B. the tests end with `wf_event_enabled=False`, such that the loaded
    lambda_function module does not have the SNS publishing enabled, and the other tests
    do not require the `workflow_event_topic` fixture to create the topic (as it will
    not be used).
    """
    if wf_event_enabled:
        expected_msg_count = 1
        monkeypatch.setenv("CIRRUS_WORKFLOW_EVENT_TOPIC_ARN", workflow_event_topic)
    else:
        expected_msg_count = 0
        monkeypatch.delenv("CIRRUS_WORKFLOW_EVENT_TOPIC_ARN", raising=False)

    event["detail"]["status"] = sfn_state
    update_state(event, {})

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert "state_updated" in items[0]

    sns_backend = sns_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    all_sent_notifications = sns_backend.topics[workflow_event_topic].sent_notifications

    assert len(all_sent_notifications) == expected_msg_count
    if wf_event_enabled:
        wfevent = WorkflowEvent.from_message_str(all_sent_notifications[0][1])
        # This works because update-state WFEventTypes happen to
        # have the same value as the associated SfnStatus.  If this changes, a
        # SfnStatus_to_WFEventType mapping would be needed.
        assert wfevent.event_type == sfn_state
        assert wfevent.payload_id == EVENT_PAYLOAD_ID
        if sfn_state == SfnStatus.FAILED:
            assert wfevent.error is not None


@pytest.mark.parametrize("publish_enabled", [True, False])
def test_success(event, statedb, publish_topic, publish_enabled, monkeypatch):
    if publish_enabled:
        expected_msg_count = 1
        monkeypatch.setenv("CIRRUS_PUBLISH_TOPIC_ARN", publish_topic)
    else:
        expected_msg_count = 0
        monkeypatch.delenv("CIRRUS_PUBLISH_TOPIC_ARN", raising=False)

    # Event needs an output payload to publish, so just use the input payload
    event["detail"]["output"] = event["detail"]["input"]

    update_state(event, {})
    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])

    assert len(items) == 1
    assert items[0]["state_updated"].startswith("COMPLETED")

    sns_backend = sns_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    all_sent_notifications = sns_backend.topics[publish_topic].sent_notifications
    assert len(all_sent_notifications) == expected_msg_count


def test_failed(event, statedb):
    event["detail"]["status"] = "FAILED"
    event["detail"]["error"] = "UnknownError"
    event["detail"]["cause"] = (
        '{"errorMessage": "/usr/local/bin/python: No module named name-delivery-to-stac", "errorType": "UnknownError", "requestId": "fake-request-id-djdj10102jd", "stackTrace": ["  File \\"/var/task/post_batch.py\\", line 66, in lambda_handler\\n    raise exception_class(error_msg)\\n"]}'  # noqa: E501
    )
    update_state(event, {})

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("FAILED")
    assert (
        items[0]["last_error"]
        == "UnknownError: /usr/local/bin/python: No module named name-delivery-to-stac"
    )


@pytest.mark.parametrize(
    ("error", "cause"),
    [
        (
            "UnknownError",
            '{"errorMessage": "/usr/local/bin/python: No module named umbra-delivery-to-stac", "errorType": "UnknownError", "requestId": "20df8b93-a10f-44b2-8b50-72d82b01569d", "stackTrace": ["  File \\"/var/task/post_batch.py\\", line 66, in lambda_handler\\n    raise exception_class(error_msg)\\n"]}',  # noqa: E501
        ),
        (None, None),
    ],
)
def test_get_execution_error(event, error, cause):
    event["detail"]["status"] = "FAILED"
    event["detail"]["error"] = error
    event["detail"]["cause"] = cause

    extracted_error = get_execution_error(event)
    if error is not None:
        assert extracted_error == {"Error": error, "Cause": cause}
    else:
        assert extracted_error == {
            "Error": "Unknown",
            "Cause": (
                "No error cause was found in the event. Check that the 'Fail' state in "
                "the workflow step function definition includes 'ErrorPath' and "
                "'CausePath' fields that capture the error name and error cause."
            ),
        }


def test_timed_out(event, statedb):
    event["detail"]["status"] = "TIMED_OUT"
    update_state(event, {})

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("FAILED")


def test_aborted(event, statedb):
    event["detail"]["status"] = "ABORTED"
    update_state(event, {})

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("ABORTED")


@pytest.mark.parametrize(
    ("error", "expected_state"),
    [
        ("stactask.exceptions.InvalidInput", "INVALID"),
        ("cirrus.lib.errors.InvalidInput", "INVALID"),
        ("unknown", "FAILED"),
    ],
)
def test_invalid(event, statedb, monkeypatch, error, expected_state) -> None:
    # special loading of the lambda_function as a module from the
    # update-state, which is not a valid name for a package/module,
    # so that we can monkeypatch it.
    update_state(event, {})

    lambda_function = sys.modules["cirrus.lambda_functions.update_state"]
    monkeypatch.setattr(
        lambda_function,
        "get_execution_error",
        lambda _: {
            "Error": error,
            "Cause": "banana in the tailpipe",
        },
    )

    # now run with a failed payload
    event["detail"]["status"] = "FAILED"
    update_state(event, {})

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith(expected_state)


def test_multi_item_publication(
    event,
    statedb,
    publish_topic,
    monkeypatch,
):
    expected_msg_count = 11
    monkeypatch.setenv("CIRRUS_PUBLISH_TOPIC_ARN", publish_topic)

    # Event needs an output payload to publish, so just use the input payload
    payload = json.loads(event["detail"]["input"])
    assert len(payload["features"]) == 1
    payload["features"] = payload["features"] * 11
    event["detail"]["output"] = json.dumps(payload)

    update_state(event, {})
    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])

    assert len(items) == 1
    assert items[0]["state_updated"].startswith("COMPLETED")

    sns_backend = sns_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    all_sent_notifications = sns_backend.topics[publish_topic].sent_notifications
    assert len(all_sent_notifications) == expected_msg_count


# TODO: test URL input
# TODO: test URL output
# TODO: test bad payloads
