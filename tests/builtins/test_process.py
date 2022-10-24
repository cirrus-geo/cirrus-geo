import io
import json
import os

import pytest

from cirrus.test import run_function


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
        ]
    }


@pytest.fixture
def process_env(queue, statedb, workflow, payloads):
    workflow_prefix = workflow["stateMachineArn"].rsplit(":", 1)[0] + ":"
    os.environ["CIRRUS_PROCESS_QUEUE"] = queue["QueueUrl"]
    os.environ["CIRRUS_STATE_DB"] = statedb
    os.environ["CIRRUS_BASE_WORKFLOW_ARN"] = workflow_prefix
    os.environ["CIRRUS_PAYLOAD_BUCKET"] = payloads


@pytest.fixture
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
        "process": {
            "workflow": "test-workflow1",
            "output_options": {
                "path_template": "/${collection}/${year}/${month}/${day}/${id}",
                "collections": {
                    "test-collection-output": ".*",
                },
            },
            "tasks": {},
        },
        "id": "test-collection-input1/workflow-test-workflow1/test-id1",
    }


@pytest.fixture
def cirrus_statedb(process_env):
    from cirrus.lib.statedb import StateDB

    return StateDB()


def test_empty_event(process_env):
    with pytest.raises(Exception):
        run_function("process", {})


def test_single_payload(payload, process_env, stepfunctions, workflow, cirrus_statedb):
    result = run_function("process", payload)

    # we processed one payload
    assert result == 1

    # we have one step function execution
    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    # we have one item in the state database that
    # matches our input payload, and it is PROCESSING
    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    print(items)
    assert items[0]["state_updated"].startswith("PROCESSING")


def test_rerun_in_process(payload, process_env, stepfunctions, workflow):
    result = run_function("process", payload)
    # the first time we should process the one payload
    assert result == 1

    result = run_function("process", payload)
    # the second time it is skipped as PROCESSING
    assert result == 0

    # we should see only the one step function
    # execution from the first payload instance
    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1


def test_rerun_completed(payload, process_env, stepfunctions, workflow, cirrus_statedb):
    # create payload state record in COMPLETED state
    items = cirrus_statedb.set_completed(payload["id"])

    result = run_function("process", payload)
    assert result == 0

    # we should see no step function executions
    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 0

    # we have one item in the state database that
    # matches our input payload, and it is INVALID
    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("COMPLETED")


def test_rerun_completed_replace(
    payload, process_env, stepfunctions, workflow, cirrus_statedb
):
    payload["process"]["replace"] = True

    # create payload state record in COMPLETED state
    items = cirrus_statedb.set_completed(payload["id"])

    result = run_function("process", payload)
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")


def test_rerun_failed(payload, process_env, stepfunctions, workflow, cirrus_statedb):
    # create payload state record in FAILED state
    items = cirrus_statedb.set_failed(payload["id"], "failure")

    result = run_function("process", payload)
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")


def test_rerun_aborted(payload, process_env, stepfunctions, workflow, cirrus_statedb):
    # create payload state record in ABORTED state
    items = cirrus_statedb.set_aborted(payload["id"])

    result = run_function("process", payload)
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")


def test_rerun_invalid(payload, process_env, stepfunctions, workflow, cirrus_statedb):
    # create payload state record in INVALID state
    items = cirrus_statedb.set_invalid(payload["id"], "invalid")

    result = run_function("process", payload)
    assert result == 0

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 0

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("INVALID")


def test_rerun_invalid_replace(
    payload, process_env, stepfunctions, workflow, cirrus_statedb
):
    payload["process"]["replace"] = True

    # create payload state record in INVALID state
    items = cirrus_statedb.set_invalid(payload["id"], "invalid")

    result = run_function("process", payload)
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")


def test_single_payload_sqs(
    payload, process_env, sqs, queue, stepfunctions, workflow, cirrus_statedb
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
    result = run_function("process", _payload)
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
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


def test_single_payload_sqs_url(
    payload,
    process_env,
    sqs,
    queue,
    payloads,
    s3,
    stepfunctions,
    workflow,
    cirrus_statedb,
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
    result = run_function("process", _payload)
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 1


def test_single_payload_sqs_bad_format(
    payload, process_env, sqs, queue, stepfunctions, workflow, cirrus_statedb
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
        run_function("process", _payload)

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 0

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 0

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    # failed messages should remain in the queue
    assert len(messages["Messages"]) == 1


def test_single_payload_sqs_bad_json(
    process_env, sqs, queue, stepfunctions, workflow, cirrus_statedb
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
        run_function("process", _payload)

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 0

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 1


def test_double_payload_sqs(
    payload, process_env, sqs, queue, stepfunctions, workflow, cirrus_statedb
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
    result = run_function("process", _payload)
    assert result == 2

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 2

    items = cirrus_statedb.get_dbitems(payload_ids=[first_id, second_id])
    assert len(items) == 2
    assert all([item["state_updated"].startswith("PROCESSING") for item in items])

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    # we should still have a message as on 100%
    # success we rely on lambda to do the SQS delete
    assert len(messages["Messages"]) == 2


def test_duplicated_payload_sqs(
    payload, process_env, sqs, queue, stepfunctions, workflow, cirrus_statedb
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
    result = run_function("process", _payload)
    assert result == 1

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[payload["id"]])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 2


def test_double_payload_sqs_with_bad_workflow(
    payload, process_env, sqs, queue, stepfunctions, workflow, cirrus_statedb
):
    bad_workflow = "unknown-workflow"
    first_id = payload["id"]
    sqs.send_message(
        QueueUrl=queue["QueueUrl"],
        MessageBody=json.dumps(payload),
    )
    second_id = payload["id"] = payload["id"][:-1] + "2"
    payload["process"]["workflow"] = bad_workflow
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
    result = run_function("process", _payload)
    assert result == 2

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = [
        cirrus_statedb.dbitem_to_item(db_item)
        for db_item in cirrus_statedb.get_dbitems(payload_ids=[first_id, second_id])
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


def test_double_payload_sqs_with_bad_format(
    payload, process_env, sqs, queue, stepfunctions, workflow, cirrus_statedb
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
        run_function("process", _payload)

    exec_count = len(
        stepfunctions.list_executions(
            stateMachineArn=workflow["stateMachineArn"],
        )["executions"]
    )
    assert exec_count == 1

    items = cirrus_statedb.get_dbitems(payload_ids=[first_id, second_id])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("PROCESSING")

    messages = sqs.receive_message(
        QueueUrl=queue["QueueUrl"],
        VisibilityTimeout=0,
        MaxNumberOfMessages=10,
    )
    assert len(messages["Messages"]) == 1
    assert json.loads(messages["Messages"][0]["Body"])["id"] == second_id
