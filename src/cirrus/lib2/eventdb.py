import logging
import os
from datetime import datetime
from enum import Enum, unique
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger(__name__)


@unique
class StateEnum(Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    ABORTED = "ABORTED"


class EventDB:
    def __init__(
        self,
        event_db_and_table_names: Optional[str] = os.getenv(
            "CIRRUS_EVENT_DB_AND_TABLE", None
        ),
    ):
        self.tsw_client = boto3.client("timestream-write")
        self.tsq_client = boto3.client("timestream-query")
        if not event_db_and_table_names:
            raise Exception("Event DB and table name not configured.")
        db_and_table_names_array = event_db_and_table_names.split("|")
        self.event_db_name = db_and_table_names_array[0]
        self.event_table_name = db_and_table_names_array[1]

    def write_timeseries_record(
        self,
        key: Dict[str, str],
        state: StateEnum,
        event_time: str,
        last_update_ts_str: str,
    ) -> None:
        parts = key.get("collections_workflow", "").rsplit("_", 1)
        if not len(parts) == 2:
            logger.error(
                f"Event could not be recorded, key value collections_workflow was not an underscore separated value: {key.get('collections_workflow')}"
            )
            return

        collections = parts[0]
        workflow = parts[1]

        itemids = key.get("itemids")

        if not workflow or not collections or not itemids:
            logger.error(
                f"Event could not be recorded, key {key} missing 'workflow', 'collections' or 'itemids'"
            )
            return

        event_time_dt = datetime.fromisoformat(event_time)
        event_time_ms = str(int(event_time_dt.timestamp() * 1000))
        # duration_ms = str(
        #     int((isoparse(last_update_ts_str) - event_time_dt).microseconds / 1000)
        # )

        record = {
            "Dimensions": [
                {"Name": "workflow", "Value": workflow},
                {"Name": "collections", "Value": collections},
                {"Name": "item_ids", "Value": itemids},
                {"Name": "state", "Value": state.value},
            ],
            # "MeasureValueType": "BIGINT",
            "Time": event_time_ms,
            # "MeasureName": "duration_ms",
            # "MeasureValue": duration_ms,
        }

        try:
            result = self.tsw_client.write_records(
                DatabaseName=self.event_db_name,
                TableName=self.event_table_name,
                Records=[record],
            )
            logger.info(
                f"Timestream WriteRecords Status for first time: [{result['ResponseMetadata']['HTTPStatusCode']}]"
            )
        except self.tsw_client.exceptions.RejectedRecordsException as err:
            logger.error(f"For {key} Timestream RejectedRecords: {err}")
            for rr in err.response["RejectedRecords"]:
                logger.error(
                    f"For {key} Rejected Index {rr['RecordIndex']} : {rr['Reason']}"
                )
                if "ExistingVersion" in rr:
                    logger.error(
                        f"For {key} Rejected record existing version: {rr['ExistingVersion']}"
                    )
        except Exception as err:
            logger.error(f"For {key} Error: {err}")

    def _mk_query_by_bin_and_duration(self, bin_size: str, duration: str) -> str:
        """bin_size is like '1d' '1h'
        duration is like '356d' '60d'
        """
        return f"""
            WITH data AS (
                SELECT BIN(time, {bin_size}) as t, state, item_ids, count(*) as count
                FROM "{self.event_db_name}"."{self.event_table_name}"
                WHERE time BETWEEN ago({duration}) AND now()
                GROUP BY BIN(time, {bin_size}), state, item_ids
                )
            SELECT t, state, count(*) as unique_count, sum(count) as count
            FROM data
            GROUP BY t, state
            ORDER BY t, state
        """

    def _mk_hour_query(self, start: int, end: int) -> str:
        return f"""
            WITH data AS (
                SELECT ago({start}h) as t, state, item_ids, count(*) as count
                FROM "{self.event_db_name}"."{self.event_table_name}"
                WHERE time BETWEEN ago({start}h) AND ago({end}h)
                GROUP BY state, item_ids
            )
            SELECT t, state, count(*) as unique_count, sum(count) as count
            FROM data
            GROUP BY t, state
            ORDER BY t, state
        """

    def _query(self, q: str) -> Dict[str, Any]:
        return self.tsq_client.query(
            QueryString=q,
            # MaxRows=123
        )

    def query_hour(self, start: int, end: int) -> Dict[str, Any]:
        return self._query(self._mk_hour_query(start, end))

    def query_by_bin_and_duration(self, bin_size: str, duration: str) -> Dict[str, Any]:
        return self._query(self._mk_query_by_bin_and_duration(bin_size, duration))
