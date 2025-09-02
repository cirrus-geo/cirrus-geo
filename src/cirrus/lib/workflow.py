import logging

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from boto3utils import s3

from cirrus.lib.enums import StateEnum
from cirrus.lib.errors import EventsDisabledError
from cirrus.lib.eventdb import EventDB
from cirrus.lib.statedb import StateDB
from cirrus.management.exceptions import StatsUnavailableError

logger = logging.getLogger(__name__)


def get_collections_workflows(cirrus_data_bucket: str) -> list[dict[str, str]]:
    cat_url = f"s3://{cirrus_data_bucket}/catalog.json"
    logger.debug("Root catalog: %s", cat_url)
    cat = s3().read_json(cat_url)

    workflows = cat.get("cirrus", {}).get("workflows", {})
    result = []
    for collections, wf_list in workflows.items():
        for wf in wf_list:
            result.append({"collections": collections, "workflow": wf})

    return result


def get_stats(cirrus_event_db_and_table: str) -> dict[str, Any] | None:
    eventdb = EventDB(event_db_and_table_names=cirrus_event_db_and_table)
    try:
        return {
            "state_transitions": {
                "daily": _daily(eventdb.query_by_bin_and_duration("1d", "60d")),
                "hourly": _hourly(eventdb.query_by_bin_and_duration("1h", "36h")),
                "hourly_rolling": _hourly(
                    eventdb.query_hour(1, 0),
                    eventdb.query_hour(2, 1),
                ),
            },
        }
    except EventsDisabledError as e:
        raise StatsUnavailableError from e


def get_summary(
    cirrus_state_db: str,
    collections: str,
    workflow_name: str,
    since: str | None = None,
    limit: int = 100000,
) -> dict[str, Any]:
    statedb = StateDB(table_name=cirrus_state_db)
    collections_workflow = f"{collections}_{workflow_name}"
    logger.debug("Getting summary for %s", collections_workflow)
    counts = {}
    for s in StateEnum:
        counts[s.value] = statedb.get_counts(
            collections_workflow,
            state=s,
            since=since,
            limit=limit,
        )
    return {
        "collections": collections,
        "workflow": workflow_name,
        "counts": counts,
    }


def get_items(
    cirrus_state_db,
    collections,
    workflow_name,
    state=None,
    since=None,
    limit=100000,
    nextkey=None,
    sort_ascending=False,
    sort_index="updated",
):
    collections_workflow = f"{collections}_{workflow_name}"
    statedb = StateDB(table_name=cirrus_state_db)
    logger.debug(
        "Getting items for %s, state=%s, since=%s",
        collections_workflow,
        state,
        since,
    )
    items_page = statedb.get_items_page(
        collections_workflow,
        state=state,
        since=since,
        limit=limit,
        nextkey=nextkey,
        sort_ascending=sort_ascending,
        sort_index=sort_index,
    )
    return {"items": [_to_current(item) for item in items_page["items"]]}


def get_item(
    cirrus_state_db,
    collections,
    workflow_name,
    itemid,
):
    statedb = StateDB(table_name=cirrus_state_db)
    payload_id = f"{collections}/workflow-{workflow_name}/{itemid}"
    item = statedb.dbitem_to_item(statedb.get_dbitem(payload_id))
    return _to_current(item)


def _results_transform(
    results: dict[str, Any],
    timestamp_function: Callable[[str], str],
    interval: str,
) -> list[dict[str, Any]]:
    intervals: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)

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
                {
                    "state": state.value,
                    "unique_count": state_val[0],
                    "count": state_val[1],
                }
                for state in StateEnum
                if (state_val := states.get(state, (0, 0)))
            ],
        }
        for ts, states in intervals.items()
    ]


def _daily(results: dict[str, Any]) -> list[dict[str, Any]]:
    return _results_transform(results, lambda x: x.split(" ")[0], "day")


def _hourly(*rs: dict[str, Any]) -> list[dict[str, Any]]:
    combined_results: dict[str, Any] = {"Rows": []}
    for result in rs:
        combined_results["Rows"].extend(result.get("Rows", []))
    return _results_transform(
        combined_results,
        lambda x: x.replace(" ", "T").split(".")[0] + "Z",
        "hour",
    )


def _to_current(item):
    item["catid"] = item["payload_id"]
    item["catalog"] = item["payload"]
    return item
