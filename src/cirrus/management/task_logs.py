import copy
import json
import logging

from datetime import UTC, datetime

import boto3

logger = logging.getLogger(__name__)

AWS_MAX_LOG_EVENTS = 10000


def parse_log_metadata(execution_history: dict) -> dict:
    history = copy.deepcopy(execution_history)
    events = history["events"]

    event_map = {e["id"]: e for e in events}

    for event in events:
        if event["type"] not in ["TaskSucceeded", "TaskFailed"]:
            continue

        details_key = (
            "taskSucceededEventDetails"
            if event["type"] == "TaskSucceeded"
            else "taskFailedEventDetails"
        )
        details = event.get(details_key, {})
        resource_type = details.get("resourceType")

        if resource_type not in ["lambda", "batch"]:
            continue

        task_scheduled = _find_task_scheduled(event, event_map)

        if not task_scheduled:
            continue

        if resource_type == "lambda":
            metadata = _extract_lambda_metadata(task_scheduled, event)
        else:  # batch
            metadata = _extract_batch_metadata(event)

        event[details_key]["logMetadata"] = metadata

    return history


def _find_task_scheduled(event: dict, event_map: dict) -> dict | None:
    current_id = event["previousEventId"]
    while current_id != 0:
        current = event_map.get(current_id)
        if not current:
            break
        if current["type"] == "TaskScheduled":
            return current
        current_id = current["previousEventId"]
    return None


def _extract_lambda_metadata(
    task_scheduled: dict,
    task_completed: dict,
) -> dict:
    params = json.loads(task_scheduled["taskScheduledEventDetails"]["parameters"])
    function_arn = params["FunctionName"]

    # arn:aws:lambda:region:account:function:function-name
    function_name = function_arn.split(":")[-1]
    log_group = f"/aws/lambda/{function_name}"

    details_key = (
        "taskSucceededEventDetails"
        if task_completed["type"] == "TaskSucceeded"
        else "taskFailedEventDetails"
    )

    # For successful tasks, the output contains SdkResponseMetadata
    # For failed tasks, the cause contains the error details with requestId
    if task_completed["type"] == "TaskSucceeded":
        output = json.loads(task_completed[details_key]["output"])
        request_id = output["SdkResponseMetadata"]["RequestId"]
    else:
        cause = json.loads(task_completed[details_key]["cause"])
        request_id = cause["requestId"]

    start_time_ms = int(task_scheduled["timestamp"].timestamp() * 1000)
    end_time_ms = int(task_completed["timestamp"].timestamp() * 1000)

    return {
        "LogGroup": log_group,
        "lambdaRequestId": request_id,
        "StartTimeUnixMs": start_time_ms,
        "EndTimeUnixMs": end_time_ms,
    }


def _extract_batch_metadata(task_completed: dict) -> dict:
    details_key = (
        "taskSucceededEventDetails"
        if task_completed["type"] == "TaskSucceeded"
        else "taskFailedEventDetails"
    )

    # For successful tasks, the output contains Container.LogStreamName
    # For failed tasks, the cause contains the batch job details
    if task_completed["type"] == "TaskSucceeded":
        output = json.loads(task_completed[details_key]["output"])
    else:
        output = json.loads(task_completed[details_key]["cause"])

    log_stream = output["Container"]["LogStreamName"]

    return {
        "LogGroup": "/aws/batch/job",
        "logStreamName": log_stream,
    }


def get_lambda_logs(
    session: boto3.Session,
    log_group_name: str,
    request_id: str,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 20,
    next_token: str | None = None,
) -> dict:
    logs_client = session.client("logs")

    kwargs: dict = {
        "logGroupName": log_group_name,
        "filterPattern": request_id,
        "limit": min(max(limit, 1), AWS_MAX_LOG_EVENTS),
    }

    if start_time is not None:
        kwargs["startTime"] = start_time
    if end_time is not None:
        kwargs["endTime"] = end_time
    if next_token is not None:
        kwargs["nextToken"] = next_token

    response = logs_client.filter_log_events(**kwargs)
    events = response.get("events", [])

    logs: dict = {"logs": []}
    for event in events:
        logs["logs"].append(
            {"timestamp": event.get("timestamp"), "message": event.get("message")},
        )
    if "nextToken" in response:
        logs["nextToken"] = response["nextToken"]
    return logs


def get_batch_logs(
    session: boto3.Session,
    log_stream_name: str,
    log_group_name: str = "/aws/batch/job",
    limit: int = 20,
    next_token: str | None = None,
) -> dict:
    logs_client = session.client("logs")

    kwargs: dict = {
        "logGroupName": log_group_name,
        "logStreamName": log_stream_name,
        "startFromHead": True,
        "limit": limit,
    }

    if next_token is not None:
        kwargs["nextToken"] = next_token

    response = logs_client.get_log_events(**kwargs)
    events = response.get("events", [])
    next_forward_token = response.get("nextForwardToken")

    logs: dict = {"logs": []}
    for event in events:
        logs["logs"].append(
            {"timestamp": event.get("timestamp"), "message": event.get("message")},
        )

    # If we're at the end, next_forward_token will be the same as next_token
    if next_forward_token != next_token and len(events) > 0:
        logs["nextToken"] = next_forward_token

    return logs


def format_log_event(log_event: dict) -> str:
    timestamp = datetime.fromtimestamp(log_event["timestamp"] / 1000, tz=UTC)
    message = log_event["message"].rstrip()
    return f"[{timestamp}] {message}"
