import copy
import json
import logging

from datetime import UTC, datetime

import boto3

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


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

        if metadata:
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
) -> dict | None:
    try:
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
        output = json.loads(task_completed[details_key]["output"])
        request_id = output["SdkResponseMetadata"]["RequestId"]

        start_time_ms = int(task_scheduled["timestamp"].timestamp() * 1000)
        end_time_ms = int(task_completed["timestamp"].timestamp() * 1000)

        return {
            "LogGroup": log_group,
            "lambdaRequestId": request_id,
            "StartTimeUnixMs": start_time_ms,
            "EndTimeUnixMs": end_time_ms,
        }
    except (KeyError, json.JSONDecodeError, IndexError) as e:
        logger.warning("Failed to extract Lambda metadata: %s", e)
        return None


def _extract_batch_metadata(task_completed: dict) -> dict | None:
    try:
        details_key = (
            "taskSucceededEventDetails"
            if task_completed["type"] == "TaskSucceeded"
            else "taskFailedEventDetails"
        )
        output = json.loads(task_completed[details_key]["output"])

        log_stream = output["Container"]["LogStreamName"]

        return {
            "LogGroup": "/aws/batch/job",
            "logStreamName": log_stream,
        }
    except (KeyError, json.JSONDecodeError) as e:
        logger.warning("Failed to extract Batch metadata: %s", e)
        return None


def get_lambda_logs(
    session: boto3.Session,
    log_group_name: str,
    request_id: str,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[dict]:
    logs_client = session.client("logs")

    filter_pattern = f'"RequestId: {request_id}"'

    kwargs: dict = {
        "logGroupName": log_group_name,
        "filterPattern": filter_pattern,
    }

    if start_time is not None:
        kwargs["startTime"] = start_time
    if end_time is not None:
        kwargs["endTime"] = end_time

    try:
        paginator = logs_client.get_paginator("filter_log_events")
        page_iterator = paginator.paginate(**kwargs)

        all_events = []
        for page in page_iterator:
            all_events.extend(page.get("events", []))

        all_events.sort(key=lambda x: x["timestamp"])

        return all_events

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning("Log group not found: %s", log_group_name)
            return []
        raise


def get_batch_logs(
    session: boto3.Session,
    log_group_name: str,
    log_stream_name: str,
) -> list[dict]:
    logs_client = session.client("logs")

    try:
        all_events = []
        next_token = None

        while True:
            kwargs: dict = {
                "logGroupName": log_group_name,
                "logStreamName": log_stream_name,
                "startFromHead": True,
            }

            if next_token:
                kwargs["nextToken"] = next_token

            response = logs_client.get_log_events(**kwargs)
            events = response.get("events", [])

            if not events:
                break

            all_events.extend(events)

            next_forward_token = response.get("nextForwardToken")
            if next_forward_token == next_token:
                break

            next_token = next_forward_token

        return all_events

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning("Log stream not found: %s", log_stream_name)
            return []
        raise


def format_log_event(log_event: dict) -> str:
    timestamp = datetime.fromtimestamp(log_event["timestamp"] / 1000, tz=UTC)
    message = log_event["message"]
    return f"[{timestamp}] {message}"
