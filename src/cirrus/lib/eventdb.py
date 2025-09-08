import logging
import os

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import Any

from cirrus.lib.enums import StateEnum
from cirrus.lib.errors import EventsDisabledError
from cirrus.lib.utils import PAYLOAD_ID_REGEX, get_client

logger = logging.getLogger(__name__)


class EventDB:
    def __init__(
        self,
        event_db_and_table_names: str | None = None,
    ):
        self.tsw_client = get_client("timestream-write")
        self.tsq_client = get_client("timestream-query")

        if event_db_and_table_names is None:
            event_db_and_table_names = os.getenv("CIRRUS_EVENT_DB_AND_TABLE")

        if event_db_and_table_names:
            db_and_table_names_array = event_db_and_table_names.split("|")
            if len(db_and_table_names_array) != 2:
                raise Exception(
                    "Event DB and table name not configured correctly, "
                    "must be a pipe-separated value of the database and table names.",
                )
            self.event_db_name: str | None = db_and_table_names_array[0]
            self.event_table_name: str | None = db_and_table_names_array[1]
        else:
            logger.info(
                "Event database is not configured, "
                "workflow state change events will not be recorded",
            )
            self.event_db_name = None
            self.event_table_name = None

    def enabled(self) -> bool:
        return bool(self.event_db_name and self.event_table_name)

    @classmethod
    def _payload_id_to_record_data(cls, payload_id: str) -> tuple[str, str, str]:
        if match := PAYLOAD_ID_REGEX.match(payload_id):
            # type returned from match is tuple[str | Any, ...], but we know
            # if our pattern matches we will get tuple[str, str, str]
            return match.groups()  # type: ignore
        raise ValueError("payload_id does not match expected pattern: " + payload_id)

    def write_timeseries_record(
        self,
        payload_id: str,
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> dict[str, Any] | None:
        if not self.enabled():
            return None

        collections, workflow, itemids = self._payload_id_to_record_data(payload_id)

        event_time_dt = datetime.fromisoformat(event_time)

        event_time_ms = str(int(event_time_dt.timestamp() * 1000))

        record = {
            "Dimensions": [
                {"Name": "workflow", "Value": workflow},
                {"Name": "collections", "Value": collections},
                {"Name": "item_ids", "Value": itemids},
                {"Name": "execution_arn", "Value": execution_arn},
            ],
            "Time": event_time_ms,
            "MeasureValueType": "VARCHAR",
            "MeasureName": "execution_state",
            "MeasureValue": state.value,
        }

        try:
            result = self.tsw_client.write_records(
                DatabaseName=self.event_db_name,
                TableName=self.event_table_name,
                Records=[record],
            )
            logger.info(
                "Timestream WriteRecords Status for first time: [%s]",
                result["ResponseMetadata"]["HTTPStatusCode"],
            )
            return result
        except self.tsw_client.exceptions.RejectedRecordsException as err:
            logger.error("For %s Timestream RejectedRecords: %s", payload_id, err)
            for rr in err.response["RejectedRecords"]:
                logger.error(
                    "For %s Rejected Index %s : %s",
                    payload_id,
                    rr["RecordIndex"],
                    rr["Reason"],
                )
                if "ExistingVersion" in rr:
                    logger.error(
                        "For %s Rejected record existing version: %s",
                        payload_id,
                        rr["ExistingVersion"],
                    )
            raise err
        except Exception as err:
            logger.error("For %s Error: %s", payload_id, err)
            raise err

    @staticmethod
    def _mk_query_by_bin_and_duration(
        bin_size: str,
        duration: str,
        event_db_name: str | None,
        event_table_name: str | None,
    ) -> str | None:
        """bin_size is like '1d' '1h'
        duration is like '356d' '60d'
        """
        if not event_db_name or not event_table_name:
            return None
        return f"""
            WITH data AS (
                SELECT
                    BIN(time, {bin_size}) as t,
                    measure_value::varchar as state,
                    item_ids,
                    count(*) as count
                FROM "{event_db_name}"."{event_table_name}"
                WHERE
                    measure_name = 'execution_state'
                    AND time BETWEEN ago({duration}) AND now()
                GROUP BY BIN(time, {bin_size}), measure_value::varchar, item_ids
                )
            SELECT t, state, count(*) as unique_count, sum(count) as count
            FROM data
            GROUP BY t, state
            ORDER BY t, state
        """  # noqa: S608

    @staticmethod
    def _mk_hour_query(
        start: int,
        end: int,
        event_db_name: str | None,
        event_table_name: str | None,
    ) -> str | None:
        if not event_db_name or not event_table_name:
            return None
        return f"""
            WITH data AS (
                SELECT
                    ago({start}h) as t,
                    measure_value::varchar as state,
                    item_ids,
                    count(*) as count
                FROM "{event_db_name}"."{event_table_name}"
                WHERE
                    measure_name = 'execution_state'
                    AND time BETWEEN ago({start}h) AND ago({end}h)
                GROUP BY measure_value::varchar, item_ids
            )
            SELECT t, state, count(*) as unique_count, sum(count) as count
            FROM data
            GROUP BY t, state
            ORDER BY t, state
        """  # noqa: S608

    def _query(self, q: str | None) -> dict[str, Any]:
        if not self.enabled():
            raise EventsDisabledError
        return self.tsq_client.query(QueryString=q)

    def query_hour(self, start: int, end: int) -> dict[str, Any]:
        return self._query(
            self._mk_hour_query(start, end, self.event_db_name, self.event_table_name),
        )

    def query_by_bin_and_duration(
        self,
        bin_size: str,
        duration: str,
    ) -> dict[str, Any]:
        return self._query(
            self._mk_query_by_bin_and_duration(
                bin_size,
                duration,
                self.event_db_name,
                self.event_table_name,
            ),
        )


def results_transform(
    results: dict[str, Any],
    timestamp_function: Callable[[str], str],
    interval: str,
) -> list[dict[str, Any]]:
    """Transform TimeStream query results into standardized format.

    Args:
        results: Raw results from TimeStream query
        timestamp_function: Function to transform timestamp strings
        interval: Time interval type ("day" or "hour")

    Returns:
        List of transformed result dictionaries with period, interval, and states
    """
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


def daily(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform daily aggregated TimeStream results."""
    return results_transform(results, lambda x: x.split(" ")[0], "day")


def hourly(*rs: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform hourly aggregated TimeStream results.

    Can handle multiple result sets by combining them.
    """
    combined_results: dict[str, Any] = {"Rows": []}
    for result in rs:
        combined_results["Rows"].extend(result.get("Rows", []))
    return results_transform(
        combined_results,
        lambda x: x.replace(" ", "T").split(".")[0] + "Z",
        "hour",
    )
