import json

import pytest
from moto import mock_logs

from cirrus.test import run_task


def test_empty_event():
    with pytest.raises(Exception):
        run_task("post-batch", {})


@mock_logs
def test_error_handling():
    with pytest.raises(
        Exception, match=r"Unable to get error log: Cause is not defined"
    ):
        run_task("post-batch", {"error": {}})

    with pytest.raises(Exception, match=r"Unable to get error log: Attempts is empty"):
        run_task("post-batch", {"error": {"Cause": "{}"}})

    with pytest.raises(Exception, match=r"Unable to get error log: Attempts is empty"):
        run_task("post-batch", {"error": {"Cause": json.dumps({"Attempts": []})}})

    with pytest.raises(
        Exception,
        match=r"Unable to get error log: Container for last Attempt is missing",
    ):
        run_task("post-batch", {"error": {"Cause": json.dumps({"Attempts": [{}]})}})

    with pytest.raises(
        Exception,
        match=r"Unable to get error log: LogStreamName for last Attempt is missing",
    ):
        run_task(
            "post-batch",
            {"error": {"Cause": json.dumps({"Attempts": [{"Container": {}}]})}},
        )

    with pytest.raises(
        Exception,
        match=r"Unable to get error log: LogStreamName for last Attempt is missing",
    ):
        run_task(
            "post-batch",
            {
                "error": {
                    "Cause": json.dumps(
                        {"Attempts": [{"Container": {"LogStreamName": ""}}]}
                    )
                }
            },
        )

    with pytest.raises(
        Exception,
        match=r"Unable to get error log, container likely never ran. Container Reason: None; Status Reason: None",
    ):
        run_task(
            "post-batch",
            {
                "error": {
                    "Cause": json.dumps(
                        {"Attempts": [{"Container": {"LogStreamName": "foobar"}}]}
                    )
                }
            },
        )

    with pytest.raises(
        Exception,
        match=r"Unable to get error log, container likely never ran. Container Reason: DockerTimeoutError: Could not transition to created; timed out after waiting 4m0s; Status Reason: Task failed to start",
    ):
        run_task(
            "post-batch",
            {
                "error": {
                    "Cause": json.dumps(
                        {
                            "Attempts": [
                                {
                                    "Container": {
                                        "LogStreamName": "cirrus-es-prod-Sentinel2/default/a6768fc4fce04b809905ff65e71a9b38",
                                        "Reason": "DockerTimeoutError: Could not transition to created; timed out after waiting 4m0s",
                                    },
                                    "StatusReason": "Task failed to start",
                                }
                            ]
                        }
                    )
                }
            },
        )
