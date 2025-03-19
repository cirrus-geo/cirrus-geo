import io
import json
import os

import botocore.exceptions
import pytest

from cirrus.lambda_functions.process import lambda_handler as process
from cirrus.lib.events import WorkflowEventManager
from cirrus.lib.process_payload import ProcessPayload, ProcessPayloads
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.sns.models import sns_backends


def assert_sns_message_sequence(expected, topic):
    sns_backend = sns_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    notifications = list(sns_backend.topics[topic].sent_notifications)
    messages = [json.loads(x[1]) for x in notifications]
    event_types = [x["event_type"] for x in messages]
    assert event_types == expected


def sqs_to_event(sqs_resp, sqs_arn):
    def lowercase_keys(_dict):
        out = {}
        for k, v in _dict.items():
            out[(k[0].lower() + k[1:])] = v
        return out

    def add_event_info(_dict):
        _dict["eventSource"] = "aws:sqs"
        _dict["eventSourceARN"] = sqs_arn
        return _dict

    return {
        "Records": [
            add_event_info(lowercase_keys(message)) for message in sqs_resp["Messages"]
        ],
    }


@pytest.fixture(autouse=True)
def _process_env(_environment, workflow, workflow_event_topic):
    workflow_prefix = workflow["stateMachineArn"].rsplit(":", 1)[0] + ":"
    os.environ["CIRRUS_BASE_WORKFLOW_ARN"] = workflow_prefix
    os.environ["CIRRUS_WORKFLOW_EVENT_TOPIC_ARN"] = workflow_event_topic


@pytest.fixture()
def payload():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "test-id1",
                "collection": "test-collection-input1",
                "properties": {},
                "assets": {},
                "links": [],
            },
        ],
        "process": [
            {
                "workflow": "test-workflow1",
                "upload_options": {
                    "path_template": "/${collection}/${year}/${month}/${day}/${id}",
                    "collections": {
                        "test-collection-output": ".*",
                    },
                },
                "tasks": {},
            },
        ],
        "id": "test-collection-input1/workflow-test-workflow1/test-id1",
    }


def test_empty_event(workflow_event_topic):
    with pytest.raises(Exception):
        process({}, {})


def test_single_payload(
    payload,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    result = process(payload, {})

    # we processed one payload
    assert result == 1

    # we have one step function execution
    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    # we have one item in the state database that
    # matches our input payload, and it is PROCESSING
    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_no_payload_bucket(
    payload,
    stepfunctions,
    workflow,
    eventdb,
    workflow_event_topic,
    monkeypatch,
):
    monkeypatch.delenv("CIRRUS_PAYLOAD_BUCKET")
    with pytest.raises(ValueError):
        _ = process(payload, {})


def test_rerun_in_process(
    payload,
    stepfunctions,
    workflow,
    eventdb,
    workflow_event_topic,
):
    result = process(payload, {})
    # the first time we should process the one payload
    assert result == 1

    result = process(payload, {})
    # the second time it is skipped as PROCESSING
    assert result == 0

    # we should see only the one step function
    # execution from the first payload instance
    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING", "ALREADY_PROCESSING"],
        workflow_event_topic,
    )


def test_simulate_race_to_in_process_client_error(
    payload,
    stepfunctions,
    workflow,
    eventdb,
    workflow_event_topic,
    mocker,
):
    def raises_client_error(*args, **kwargs):
        raise botocore.exceptions.ClientError(
            error_response={"Error": {"Code": "ConditionalCheckFailedException"}},
            operation_name="monkeying around",
        )

    wfem_claim = mocker.patch(
        "cirrus.lib.events.WorkflowEventManager.claim_processing",
    )
    wfem_claim.side_effect = raises_client_error

    result = process(payload, {})
    # the second time it is skipped as PROCESSING
    assert result == 0

    # we should see only the one step function
    # execution from the first payload instance
    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )

    # because we faked the payload already getting to PROCESSING,
    # and thus not starting an exection
    assert exec_count == 0

    assert_sns_message_sequence(
        ["ALREADY_PROCESSING"],
        workflow_event_topic,
    )


def test_rerun_completed(
    payload,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    # create payload state record in COMPLETED state
    items = statedb.set_completed(payload["id"])

    result = process(payload, {})
    assert result == 0

    # we should see no step function executions
    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 0

    # we have one item in the state database that
    # matches our input payload, and it is INVALID
    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("COMPLETED")
    assert_sns_message_sequence(["ALREADY_COMPLETED"], workflow_event_topic)


def test_rerun_completed_replace(
    payload,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    payload["process"][0]["replace"] = True

    # create payload state record in COMPLETED state
    items = statedb.set_completed(payload["id"])

    result = process(payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_rerun_failed(payload, stepfunctions, workflow, statedb, workflow_event_topic):
    # create payload state record in FAILED state
    items = statedb.set_failed(payload["id"], "failure")

    result = process(payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_rerun_aborted(payload, stepfunctions, workflow, statedb, workflow_event_topic):
    # create payload state record in ABORTED state
    items = statedb.set_aborted(payload["id"])

    result = process(payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_rerun_invalid(payload, stepfunctions, workflow, statedb, workflow_event_topic):
    # create payload state record in INVALID state
    items = statedb.set_invalid(payload["id"], "invalid")

    result = process(payload, {})
    assert result == 0

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 0

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("INVALID")
    assert_sns_message_sequence(["ALREADY_INVALID"], workflow_event_topic)


def test_rerun_invalid_replace(
    payload,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    payload["process"][0]["replace"] = True

    # create payload state record in INVALID state
    items = statedb.set_invalid(payload["id"], "invalid")

    result = process(payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_single_payload_sqs(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    result = process(_payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    # we should still have a message as on 100%
    # success we rely on lambda to do the SQS delete
    assert len(messages["Messages"]) == 1
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_single_payload_no_id(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    payload_id = payload.pop("id")
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    result = process(_payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload_id])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 1
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_single_payload_sqs_url(
    payload,
    sqs,
    queue,
    payloads,
    s3,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    with io.BytesIO(json.dumps(payload).encode()) as fileobj:
        s3.upload_fileobj(fileobj, payloads, "payload.json")

    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps({"url": f"s3://{payloads}/payload.json"}),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    result = process(_payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 1
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_single_payload_sqs_bad_format(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    del payload["process"]
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    with pytest.raises(Exception):
        process(_payload, {})

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 0

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 0

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    # failed messages should remain in the queue
    assert len(messages["Messages"]) == 1
    assert_sns_message_sequence(["NOT_A_PROCESS_PAYLOAD"], workflow_event_topic)


def test_single_payload_sqs_bad_json(
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody="{'this-is-bad-json': th}",
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    with pytest.raises(Exception):
        process(_payload, {})

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 0

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 1
    assert_sns_message_sequence(["RECORD_EXTRACT_FAILED"], workflow_event_topic)


def test_double_payload_sqs(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    first_id = payload["id"]
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    second_id = payload["id"] = payload["id"][:-1] + "2"
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    result = process(_payload, {})
    assert result == 2

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 2

    items = statedb.get_dbitems(payload_ids=[first_id, second_id])
    assert len(items) == 2
    assert all(item["state_updated"].startswith("PROCESSING") for item in items)

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    # we should still have a message as on 100%
    # success we rely on lambda to do the SQS delete
    assert len(messages["Messages"]) == 2
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING"] * 2,
        workflow_event_topic,
    )


def test_duplicated_payload_sqs(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    result = process(_payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 2
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING", "DUPLICATE_ID_ENCOUNTERED"],
        workflow_event_topic,
    )


def test_double_payload_sqs_with_bad_workflow(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    bad_workflow = "unknown-workflow"
    first_id = payload["id"]
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    second_id = payload["id"] = payload["id"][:-1] + "2"
    payload["process"][0]["workflow"] = bad_workflow
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    result = process(_payload, {})
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = [
        statedb.dbitem_to_item(db_item)
        for db_item in statedb.get_dbitems(payload_ids=[first_id, second_id])
    ]
    assert len(items) == 2
    items = sorted(items, key=lambda i: i["payload_id"])
    assert items[0]["state"] == "PROCESSING"
    assert items[1]["state"] == "FAILED"

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 2
    assert_sns_message_sequence(
        ["CLAIMED_PROCESSING", "STARTED_PROCESSING", "CLAIMED_PROCESSING", "FAILED"],
        workflow_event_topic,
    )


def test_payload_bad_workflow_no_id(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    bad_workflow = "unknown-workflow"
    payload["process"][0]["workflow"] = bad_workflow
    del payload["id"]
    result = process(payload, {})
    assert result == 0

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 0
    assert_sns_message_sequence(["CLAIMED_PROCESSING", "FAILED"], workflow_event_topic)


def test_double_payload_sqs_with_bad_format(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    first_id = payload["id"]
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    second_id = payload["id"] = payload["id"][:-1] + "2"
    del payload["process"]
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    _payload = sqs_to_event(
        sqs.receive_message(
            QueueUrl=queue["QueueUrl"],
            VisibilityTimeout=0,
            MaxNumberOfMessages=10,
        ),
        queue["Arn"],
    )
    with pytest.raises(Exception):
        process(_payload, {})

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"],
    )
    assert exec_count == 1

    items = statedb.get_dbitems(payload_ids=[first_id, second_id])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 1
    assert json.loads(messages["Messages"][0]["Body"])["id"] == second_id
    assert_sns_message_sequence(
        ["NOT_A_PROCESS_PAYLOAD", "CLAIMED_PROCESSING", "STARTED_PROCESSING"],
        workflow_event_topic,
    )


def test_payload_unable_to_upload(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
    mocker,
):
    def raises_client_error(*args, **kwargs):
        raise botocore.exceptions.ClientError(
            error_response={"Error": {"Code": "403"}},
            operation_name="monkeying around",
        )

    s3_upload = mocker.patch(
        "boto3utils.s3.s3.upload_json",
    )
    s3_upload.side_effect = raises_client_error

    with pytest.raises(botocore.exceptions.ClientError, match="monkeying around"):
        _ = process(payload, {})


def test_finding_claimed_item(
    payload,
    sqs,
    queue,
    stepfunctions,
    workflow,
    statedb,
    workflow_event_topic,
):
    wfem = WorkflowEventManager()
    proc_payload = ProcessPayload(**payload)

    pre_cooked_exec_arn = (
        ProcessPayloads.gen_execution_arn(
            payload["id"],
            payload["process"][0]["workflow"],
        ).rpartition(":")[0]
        + ":from_db_entry"
    )
    proc_payload._claim(wfem, pre_cooked_exec_arn, None)
    proc_payloads = ProcessPayloads([ProcessPayload(**payload)], statedb=statedb)
    state_items = proc_payloads.get_states_and_exec_arn()
    state, exec_arn = state_items[proc_payload["id"]]
    assert state.value == "CLAIMED"
    assert exec_arn == pre_cooked_exec_arn
