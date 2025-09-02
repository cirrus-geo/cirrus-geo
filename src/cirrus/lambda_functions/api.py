import json
import os

from copy import deepcopy
from typing import Any
from urllib.parse import urljoin

from boto3utils import s3

from cirrus.lib.logging import get_task_logger
from cirrus.lib.statedb import StateDB
from cirrus.lib.workflow import get_item, get_items, get_stats, get_summary
from cirrus.management.exceptions import StatsUnavailableError

logger = get_task_logger("function.api", payload=())


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


def lambda_handler(event, _context):
    logger.debug("Event: %s", json.dumps(event))
    data_bucket = os.environ["CIRRUS_DATA_BUCKET"]
    event_db_and_table = os.environ["CIRRUS_EVENT_DB_AND_TABLE"]
    state_db = os.environ["CIRRUS_STATE_DB"]

    statedb = StateDB()

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
    since = qparams.get("since", None)
    nextkey = qparams.get("nextkey", None)
    limit = int(qparams.get("limit", 100000))
    sort_ascending = bool(int(qparams.get("sort_ascending", 0)))
    sort_index = qparams.get("sort_index", "updated")

    # `/`
    # Get links to summary endpoints for each collections + workflow
    if payload_id == "":
        return response(get_root(root_url, data_bucket))

    # `/stats`
    # Get bulk (all workflows) state transition stats
    if payload_id == "stats":
        try:
            stats = get_stats(event_db_and_table)
            return response(stats)
        except StatsUnavailableError:
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
    parts = key["collections_workflow"].rsplit("_", maxsplit=1)
    collections = parts[0]
    workflow = parts[1]

    # `/{collections}/workflow-{workflow}`
    # Get summary item (DynamoDB record) state counts for a collections + workflow
    if key["itemids"] == "":
        return response(
            get_summary(
                state_db,
                collections,
                workflow,
                since=since,
                limit=limit,
            ),
        )

    # `/{collections}/workflow-{workflow}/{itemids}`
    # Get list of items (DynamoDB records) for a collections + workflow
    if key["itemids"] == "items":
        return response(
            get_items(
                state_db,
                collections,
                workflow,
                state=state,
                since=since,
                limit=limit,
                nextkey=nextkey,
                sort_ascending=sort_ascending,
                sort_index=sort_index,
            ),
        )

    # `/{collections}/workflow-{workflow}/{itemid}`
    # Get a single item (DynamoDB record) for a collections + workflow + itemid
    return response(
        get_item(
            state_db,
            collections,
            workflow,
            key["itemids"],
        ),
    )
