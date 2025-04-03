import json

import moto
import pytest

from cirrus.lambda_functions.post_batch import lambda_handler as post_batch


def test_empty_event():
    with pytest.raises(Exception):
        post_batch({}, {})


@moto.mock_aws
def test_error_handling():
    with pytest.raises(
        Exception,
        match=r"Unable to get error log: Cause is not defined",
    ):
        post_batch({"error": {}}, {})

    with pytest.raises(Exception, match=r"Unable to get error log: Attempts is empty"):
        post_batch({"error": {"Cause": "{}"}}, {})

    with pytest.raises(Exception, match=r"Unable to get error log: Attempts is empty"):
        post_batch({"error": {"Cause": json.dumps({"Attempts": []})}}, {})

    with pytest.raises(
        Exception,
        match=r"Unable to get error log: Container for last Attempt is missing",
    ):
        post_batch({"error": {"Cause": json.dumps({"Attempts": [{}]})}}, {})

    with pytest.raises(
        Exception,
        match=r"Unable to get error log: LogStreamName for last Attempt is missing",
    ):
        post_batch(
            {"error": {"Cause": json.dumps({"Attempts": [{"Container": {}}]})}},
            {},
        )

    with pytest.raises(
        Exception,
        match=r"Unable to get error log: LogStreamName for last Attempt is missing",
    ):
        post_batch(
            {
                "error": {
                    "Cause": json.dumps(
                        {"Attempts": [{"Container": {"LogStreamName": ""}}]},
                    ),
                },
            },
            {},
        )

    with pytest.raises(
        Exception,
        match=(
            r"Unable to get error log, container likely never ran. "
            r"Container Reason: None; Status Reason: None"
        ),
    ):
        post_batch(
            {
                "error": {
                    "Cause": json.dumps(
                        {"Attempts": [{"Container": {"LogStreamName": "foobar"}}]},
                    ),
                },
            },
            {},
        )

    with pytest.raises(
        Exception,
        match=(
            r"Unable to get error log, container likely never ran. "
            r"Container Reason: DockerTimeoutError: Could not transition to created; "
            r"timed out after waiting 4m0s; Status Reason: Task failed to start"
        ),
    ):
        post_batch(
            {
                "error": {
                    "Cause": json.dumps(
                        {
                            "Attempts": [
                                {
                                    "Container": {
                                        "LogStreamName": (
                                            "cirrus-es-prod-Sentinel2/default/"
                                            "a6768fc4fce04b809905ff65e71a9b38"
                                        ),
                                        "Reason": (
                                            "DockerTimeoutError: Could not transition "
                                            "to created; timed out after waiting 4m0s"
                                        ),
                                    },
                                    "StatusReason": "Task failed to start",
                                },
                            ],
                        },
                    ),
                },
            },
            {},
        )
