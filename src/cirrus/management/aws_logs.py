import copy
import json
import logging

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
