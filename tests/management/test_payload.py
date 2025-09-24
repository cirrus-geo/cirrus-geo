import json

import pytest

from cirrus.management.commands.payload import get_id, validate

MOCK_PAYLOAD = {
    "type": "FeatureCollection",
    "process": [
        {
            "workflow": "test-workflow",
            "upload_options": {},
            "tasks": {
                "task_name": {},
            },
            "workflow_options": {
                "an_option": "0000000000",
            },
        },
    ],
    "features": [
        {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": "test-01_2024-10-01-07-01-48",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [
                            53.12579764470497,
                            16.716572734586094,
                        ],
                        [
                            53.08030088995125,
                            16.727463448067468,
                        ],
                        [
                            53.06900659219337,
                            16.683619747456305,
                        ],
                        [
                            53.11449360780934,
                            16.672731472452575,
                        ],
                        [
                            53.12579764470497,
                            16.716572734586094,
                        ],
                    ],
                ],
            },
            "bbox": [
                53.06900659219337,
                16.672731472452575,
                53.12579764470497,
                16.727463448067468,
            ],
            "properties": {
                "datetime": "2024-10-31T07:05:49.400252Z",
                "end_datetime": "2024-10-31T07:05:50.800503Z",
                "platform": "satellite-999",
                "created": "2025-01-02T21:03:41.052Z",
                "updated": "2025-01-03T20:12:19.446Z",
            },
            "links": [
                {
                    "rel": "self",
                    "href": "https://stac.testing.com/collections/sar-test/items/test-01_2024-10-01-07-01-48",
                    "type": "application/json",
                },
            ],
            "assets": {},
            "collection": "sar-test",
        },
    ],
}


@pytest.fixture
def payload(invoke):
    def _payload(cmd):
        return invoke("payload " + cmd)

    return _payload


def test_payload(payload):
    result = payload("")
    assert result.exit_code == 2
    assert result.output.startswith("Usage: cirrus payload ")


def test_payload_get_id(runner):
    result = runner.invoke(get_id, input=json.dumps(MOCK_PAYLOAD))

    assert result.exit_code == 0
    assert (
        result.stdout.strip()
        == "sar-test/workflow-test-workflow/test-01_2024-10-01-07-01-48"
    )


def test_payload_validate(runner):
    MOCK_PAYLOAD["id"] = "collection/workflow-test-id/itemid"
    result = runner.invoke(validate, input=json.dumps(MOCK_PAYLOAD))
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_payload_validate_bad_payload(runner):
    MOCK_PAYLOAD.pop("process")
    result = runner.invoke(validate, input=json.dumps(MOCK_PAYLOAD))
    assert result.exit_code == 1
    assert (
        result.exc_info[1].args[0]
        == "Payload must contain a 'process' array of process definitions"
    )
