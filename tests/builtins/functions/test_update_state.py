import pytest

from cirrus.test import run_function

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
        "account": "608149789419",
        "time": "2022-11-09T00:17:18Z",
        "region": "us-east-1",
        "resources": [
            "arn:aws:states:us-east-1:123456789012:execution:test-workflow1:ef3ace61-4231-4488-9f55-17956ede0de7"
        ],
        "detail": {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-workflow1:ef3ace61-4231-4488-9f55-17956ede0de7",
            "stateMachineArn": "arn:aws:states:us-east-1:123456789012:stateMachine:test-workflow1",
            "name": "ef3ace61-4231-4488-9f55-17956ede0de7",
            "status": "SUCCEEDED",
            "startDate": 1667953034792,
            "stopDate": 1667953037547,
            "input": '{"id": "'
            + EVENT_PAYLOAD_ID
            + '", "metadata_href": "s3://sentinel-s2-l2a/tiles/31/T/DG/2017/9/10/0/tileInfo.json", "process": {"workflow": "sentinel2-to-stac", "input_collections": ["roda-sentinel2"], "upload_options": {"path_template": "${earthsearch:s3_path}", "public_assets": "ALL"}, "tasks": {"sentinel2-to-stac": {}}}}',
            "output": None,
            "inputDetails": {"included": True},
            "outputDetails": None,
        },
    }


def test_empty_event():
    with pytest.raises(Exception):
        run_function("update-state", {})


def test_success(event, statedb):
    run_function("update-state", event)

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("COMPLETED")


def test_failed(event, statedb):
    event["detail"]["status"] = "FAILED"
    run_function("update-state", event)

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("FAILED")


def test_timed_out(event, statedb):
    event["detail"]["status"] = "TIMED_OUT"
    run_function("update-state", event)

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("FAILED")


def test_aborted(event, statedb):
    event["detail"]["status"] = "ABORTED"
    run_function("update-state", event)

    items = statedb.get_dbitems(payload_ids=[EVENT_PAYLOAD_ID])
    assert len(items) == 1
    assert items[0]["state_updated"].startswith("ABORTED")


# TODO: test INVALID (requires get-execution-history to resolve InvalidError)
# TODO: test URL input
# TODO: test URL output
# TODO: test bad payloads
