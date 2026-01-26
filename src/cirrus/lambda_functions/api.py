import json
import os

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from boto3utils import s3

from cirrus.lib.enums import StateEnum
from cirrus.lib.errors import EventsDisabledError
from cirrus.lib.eventdb import EventDB, daily, hourly
from cirrus.lib.events import (
    WorkflowMetric,
    WorkflowMetricReader,
    WorkflowMetricSeries,
    date_formatter,
)
from cirrus.lib.logging import CirrusLoggerAdapter
from cirrus.lib.statedb import StateDB, to_current
from cirrus.lib.utils import parse_since

logger = CirrusLoggerAdapter("function.api")


def query_hour(
    metric_reader: WorkflowMetricReader,
    start: int,
    end: int,
) -> list[WorkflowMetric]:
    """
    Query CloudWatch metrics for a specific hour range.
    """
    now = datetime.now(UTC)
    end_time = now - timedelta(hours=end)
    start_time = now - timedelta(hours=start)
    return metric_reader.aggregated_by_event_type(
        start_time=start_time,
        end_time=end_time,
        period=3600,
        formatter=date_formatter(),
    )


def relative_params_to_absolutes(
    bin_size: str,
    duration: str,
) -> tuple[datetime, datetime, str, int]:
    """
    Query CloudWatch metrics for a given bin size and duration.
    bin_size: e.g. '1d', '1h'
    duration: e.g. '30d', '7d'
    """
    delta = parse_since(duration)
    period = int(parse_since(bin_size).total_seconds())
    if (granularity := bin_size[-1]) not in "dhms":
        raise ValueError(f"Unknown temporal granularity suffix ({granularity})")

    end_time = datetime.now(UTC)
    if granularity == "d":
        end_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time += timedelta(days=1)  # include the current day
    elif granularity == "h":
        end_time = end_time.replace(minute=0, second=0, microsecond=0)
        end_time += timedelta(hours=1)  # include the current hour
    else:
        end_time = end_time.replace(second=0, microsecond=0)
        end_time += timedelta(minutes=1)  # include the current minute

    start_time = end_time - delta - timedelta(seconds=period)

    return start_time, end_time, granularity, period


def query_by_bin_and_duration(
    metric_reader: WorkflowMetricReader,
    bin_size: str,
    duration: str,
) -> list[WorkflowMetric]:
    start_time, end_time, granularity, period = relative_params_to_absolutes(
        bin_size,
        duration,
    )

    return metric_reader.aggregated_by_event_type(
        start_time=start_time,
        end_time=end_time,
        period=period,
        formatter=date_formatter(granularity=granularity),
    )


def query_by_bin_duration_and_workflows(
    metric_reader: WorkflowMetricReader,
    bin_size: str,
    duration: str,
    workflows: list[str],
) -> list[WorkflowMetricSeries]:
    start_time, end_time, granularity, period = relative_params_to_absolutes(
        bin_size,
        duration,
    )
    return metric_reader.aggregated_for_specified_workflows(
        workflows=workflows,
        start_time=start_time,
        end_time=end_time,
        period=period,
        formatter=date_formatter(granularity=granularity),
    )


def response(
    body: str | dict[str, Any],
    status_code: int = 200,
    headers: dict[str, str] | None = None,
):
    _headers = {} if headers is None else deepcopy(headers)

    # CORS headers
    _headers.update(
        {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
        },
    )
    return {"statusCode": status_code, "headers": _headers, "body": json.dumps(body)}


def create_link(url, title, rel, media_type="application/json"):
    return {"title": title, "rel": rel, "type": media_type, "href": url}


def get_root(root_url, data_bucket):
    cat_url = f"s3://{data_bucket}/catalog.json"
    logger.debug("Root catalog: %s", cat_url)
    cat = s3().read_json(cat_url)

    links = []
    workflows = cat.get("cirrus", {}).get("workflows", {})
    for col in workflows:
        for wf in workflows[col]:
            name = f"{col} - {wf}"
            link = create_link(
                urljoin(
                    root_url,
                    f"{col}/workflow-{wf}",
                ),
                name,
                "child",
            )
            links.append(link)

    links.insert(0, create_link(root_url, "home", "self"))
    links.append(create_link(cat_url, "STAC", "stac"))

    return {
        "id": f"{cat['id']}-state-api",
        "description": f"{cat['description']} State API",
        "links": links,
    }


def filter_for_dashboard(
    data: list[WorkflowMetric] | None,
    interval: str,
) -> list[dict[str, Any]] | None:
    filtered = []
    """compatibilty layer to reformat WorkflowMetricReader response in the same fashion
    that EventDB reported.

    Arguments:
      data (list[WorkflowMetric]): list of dicts from WorkflowMetricReader
      interval (str): interval label to add to each entry (e.g. 'daily', 'hourly')
    """

    if data is None:
        return None

    def events_to_states(events: dict[str, int]) -> list[dict[str, Any]]:
        # this function passes through all WFEventTypes, but updates the names for
        # COMPLETED and CLAIMED_PROCESSING to be SUCCEEDED and CLAIMED, respectively
        state_map = {
            "SUCCEEDED": "COMPLETED",
            "CLAIMED_PROCESSING": "CLAIMED",
            "STARTED_PROCESSING": "PROCESSING",
        }

        return [
            {
                "state": state_map.get(event, event),
                "unique_count": value,
                "count": value,
            }
            for event, value in events.items()
            if event in StateEnum or event in state_map
        ]

    for entry in data:
        filtered.append(
            {
                "period": entry["period"],
                "states": events_to_states(entry["events"]),
                "interval": interval,
            },
        )

    return filtered


def get_stats(
    _metricreader: WorkflowMetricReader,
    _eventdb: EventDB,
) -> dict[str, Any] | None:
    logger.debug("Get stats")

    if _metricreader.enabled():
        return {
            "state_transitions": {
                "daily": filter_for_dashboard(
                    query_by_bin_and_duration(_metricreader, "1d", "60d"),
                    "day",
                ),
                "hourly": filter_for_dashboard(
                    query_by_bin_and_duration(_metricreader, "1h", "36h"),
                    "hour",
                ),
                "hourly_rolling": filter_for_dashboard(
                    (query_hour(_metricreader, 1, 0) or [])
                    + (query_hour(_metricreader, 2, 1) or []),
                    "hour",
                ),
            },
        }

    try:
        return {
            "state_transitions": {
                "daily": daily(_eventdb.query_by_bin_and_duration("1d", "60d")),
                "hourly": hourly(_eventdb.query_by_bin_and_duration("1h", "36h")),
                "hourly_rolling": hourly(
                    _eventdb.query_hour(1, 0),
                    _eventdb.query_hour(2, 1),
                ),
            },
        }
    except EventsDisabledError:
        return None


def summary(collections_workflow, since, limit, statedb):
    parts = collections_workflow.rsplit("_", maxsplit=1)
    logger.debug("Getting summary for %s", collections_workflow)
    counts = {}
    for s in StateEnum:
        counts[s] = statedb.get_counts(
            collections_workflow,
            state=s,
            since=since,
            limit=limit,
        )
    return {"collections": parts[0], "workflow": parts[1], "counts": counts}


def lambda_handler(event, _context):
    logger.debug("Event: %s", json.dumps(event))
    data_bucket = os.getenv("CIRRUS_DATA_BUCKET", None)

    # Cirrus state database
    statedb = StateDB()
    eventdb = EventDB()
    metric_reader = WorkflowMetricReader()

    # get request URL
    domain = event.get("requestContext", {}).get("domainName", "")
    path = None
    if domain != "":
        path = event.get("requestContext", {}).get("path", "")
        root_url = f"https://{domain}{path}/"
    else:
        root_url = None

    # get path parameters
    stage = event.get("requestContext", {}).get("stage", "")

    parts = [p for p in event.get("path", "").split("/") if p != ""]
    if len(parts) > 0 and parts[0] == stage:
        parts = parts[1:]
    payload_id = "/".join(parts)
    logger.info("Path parameters: %s", payload_id)

    # get query parameters
    qparams = (
        event["queryStringParameters"] if event.get("queryStringParameters") else {}
    )
    logger.info("Query Parameters: %s", qparams)
    state = qparams.get("state", None)
    since_str = qparams.get("since", None)
    since = parse_since(since_str) if since_str else None
    nextkey = qparams.get("nextkey", None)
    limit = int(qparams.get("limit", 100000))
    sort_ascending = bool(int(qparams.get("sort_ascending", 0)))
    sort_index = qparams.get("sort_index", "updated")

    # root endpoint
    if payload_id == "":
        return response(get_root(root_url, data_bucket))

    if payload_id == "stats":
        if stats := get_stats(_metricreader=metric_reader, _eventdb=eventdb):
            return response(stats)
        return response(
            {
                "error": (
                    "Endpoint /stats is not enabled because "
                    "timeseries database is not configured",
                ),
            },
            404,
        )

    if "/workflow-" not in payload_id:
        return response(f"{path} not found", status_code=400)

    key = statedb.payload_id_to_key(payload_id)

    if key["itemids"] == "":
        # get summary of collection
        return response(
            summary(
                key["collections_workflow"],
                since=since,
                limit=limit,
                statedb=statedb,
            ),
        )

    if key["itemids"] == "items":
        # get items
        logger.debug(
            "Getting items for %s, state=%s, since=%s",
            key["collections_workflow"],
            state,
            since_str,
        )
        items = statedb.get_items_page(
            key["collections_workflow"],
            state=state,
            since=since,
            limit=limit,
            nextkey=nextkey,
            sort_ascending=sort_ascending,
            sort_index=sort_index,
        )
        return response(
            {"items": [to_current(item) for item in items["items"]]},
        )

    # get individual item
    item = statedb.dbitem_to_item(statedb.get_dbitem(payload_id))
    return response(to_current(item))
