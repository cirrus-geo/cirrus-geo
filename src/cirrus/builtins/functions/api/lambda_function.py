import json
import os
from collections import defaultdict
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

from boto3utils import s3

from cirrus.lib2.eventdb import EventDB
from cirrus.lib2.logging import get_task_logger
from cirrus.lib2.statedb import STATES, StateDB

logger = get_task_logger("function.api", payload=tuple())

# envvars
DATA_BUCKET = os.getenv("CIRRUS_DATA_BUCKET", None)

# Cirrus state database
statedb = StateDB()
eventdb = EventDB()


def response(
    body: Union[str, Dict[str, Any]],
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
):
    if headers is None:
        _headers = {}
    else:
        _headers = deepcopy(headers)

    # CORS headers
    _headers.update(
        {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Credentials": "true"}
    )
    return {"statusCode": status_code, "headers": _headers, "body": json.dumps(body)}


def create_link(url, title, rel, media_type="application/json"):
    return {"title": title, "rel": rel, "type": media_type, "href": url}


def get_root(root_url):
    cat_url = f"s3://{DATA_BUCKET}/catalog.json"
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

    root = {
        "id": f"{cat['id']}-state-api",
        "description": f"{cat['description']} State API",
        "links": links,
    }

    return root


def get_stats(_eventdb: EventDB) -> Optional[Dict[str, Any]]:
    logger.debug("Get stats")

    if _eventdb.enabled():
        return {
            "state_transitions": {
                "daily": daily(_eventdb.query_by_bin_and_duration("1d", "60d")),
                "hourly": hourly(_eventdb.query_by_bin_and_duration("1h", "36h")),
                "hourly_rolling": hourly(
                    _eventdb.query_hour(1, 0), _eventdb.query_hour(2, 1)
                ),
            }
        }
    else:
        return None


def _results_transform(
    results: Dict[str, Any], timestamp_function: Callable[[str], str], interval: str
) -> List[Dict[str, Any]]:
    intervals: Dict[str, Dict[str, Tuple[int, int]]] = defaultdict(dict)

    for row in results["Rows"]:
        ts = timestamp_function(row["Data"][0]["ScalarValue"])
        state = row["Data"][1]["ScalarValue"]
        unique_count = int(row["Data"][2]["ScalarValue"])
        total_count = int(row["Data"][3]["ScalarValue"])
        intervals[ts][state] = (unique_count, total_count)

    return [
        {
            "period": ts,
            "interval": interval,
            "states": [
                {"state": state, "unique_count": state_val[0], "count": state_val[1]}
                for state in STATES
                if (state_val := states.get(state, (0, 0)))
            ],
        }
        for ts, states in intervals.items()
    ]


def daily(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _results_transform(results, lambda x: x.split(" ")[0], "day")


def hourly(r1: Dict[str, Any], *rs: Dict[str, Any]) -> List[Dict[str, Any]]:
    combined_results = deepcopy(r1)
    for result in rs:
        combined_results["Rows"].extend(result.get("Rows", []))
    return _results_transform(
        combined_results, lambda x: x.replace(" ", "T").split(".")[0] + "Z", "hour"
    )


def summary(collections_workflow, since, limit):
    parts = collections_workflow.rsplit("_", maxsplit=1)
    logger.debug("Getting summary for %s", collections_workflow)
    counts = {}
    for s in STATES:
        counts[s] = statedb.get_counts(
            collections_workflow,
            state=s,
            since=since,
            limit=limit,
        )
    return {"collections": parts[0], "workflow": parts[1], "counts": counts}


def lambda_handler(event, _context):
    logger.debug("Event: %s", json.dumps(event))

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

    legacy = False
    if payload_id.startswith("item"):
        legacy = True
        payload_id = payload_id.replace("item/", "", 1)
    if payload_id.startswith("collections"):
        legacy = True
        payload_id = payload_id.replace("collections/", "", 1)
    logger.info("Path parameters: %s", payload_id)

    transform = to_legacy if legacy else to_current

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
    # count_limit = int(qparams.get('count_limit', 100000))
    # legacy = qparams.get('legacy', False)

    # root endpoint
    if payload_id == "":
        return response(get_root(root_url))

    if payload_id == "stats":
        if stats := get_stats(eventdb):
            return response(stats)
        else:
            return response(
                {
                    "error": "Endpoint /stats is not enabled because timeseries database is not configured"
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
            )
        )
    elif key["itemids"] == "items":
        # get items
        logger.debug(
            "Getting items for %s, state=%s, since=%s",
            key["collections_workflow"],
            state,
            since,
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
        return response({"items": [transform(item) for item in items["items"]]})
    else:
        # get individual item
        item = statedb.dbitem_to_item(statedb.get_dbitem(payload_id))
        return response(transform(item))


def to_current(item):
    item["catid"] = item["payload_id"]
    item["catalog"] = item["payload"]
    return item


def to_legacy(item):
    _item = {
        "id": item["payload_id"],
        "catid": item["payload_id"],
        "input_collections": item["collections"],
        "current_state": f"{item['state']}_{item['updated']}",
        "state": item["state"],
        "created_at": item["created"],
        "updated_at": item["updated"],
        "input_catalog": item["payload"],
    }
    if "executions" in item:
        _item["execution"] = item["executions"][-1]
    if "outputs" in item:
        _item["items"] = item["outputs"]
    if "last_error" in item:
        _item["error_message"] = item["last_error"]
    return _item
