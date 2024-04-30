import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from .enums import StateEnum
from .utils import PAYLOAD_ID_REGEX, get_client

logger = logging.getLogger(__name__)


class EventDB:
    def __init__(
        self,
        event_db_and_table_names: Optional[str] = None,
    ):
        self.tsw_client = get_client("timestream-write")
        self.tsq_client = get_client("timestream-query")

        if event_db_and_table_names is None:
            event_db_and_table_names = os.getenv("CIRRUS_EVENT_DB_AND_TABLE")

        if event_db_and_table_names:
            db_and_table_names_array = event_db_and_table_names.split("|")
            if len(db_and_table_names_array) != 2:
                raise Exception(
                    "Event DB and table name not configured correctly, must be a pipe-separated value of the database and table names."
                )
            self.event_db_name: Optional[str] = db_and_table_names_array[0]
            self.event_table_name: Optional[str] = db_and_table_names_array[1]
        else:
            logger.info(
                "Event database is not configured, workflow state change events will not be recorded"
            )
            self.event_db_name = None
            self.event_table_name = None

    def enabled(self) -> bool:
        return bool(self.event_db_name and self.event_table_name)

    @classmethod
    def _payload_id_to_record_data(cls, payload_id: str) -> Tuple[str, str, str]:
        if match := PAYLOAD_ID_REGEX.match(payload_id):
            return match.groups()
        raise ValueError("payload_id does not match expected pattern: " + payload_id)

    def write_timeseries_record(
        self,
        payload_id: str,
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> Optional[Dict[str, Any]]:
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
                f"Timestream WriteRecords Status for first time: [{result['ResponseMetadata']['HTTPStatusCode']}]"
            )
            return result
        except self.tsw_client.exceptions.RejectedRecordsException as err:
            logger.error(f"For {payload_id} Timestream RejectedRecords: {err}")
            for rr in err.response["RejectedRecords"]:
                logger.error(
                    f"For {payload_id} Rejected Index {rr['RecordIndex']} : {rr['Reason']}"
                )
                if "ExistingVersion" in rr:
                    logger.error(
                        f"For {payload_id} Rejected record existing version: {rr['ExistingVersion']}"
                    )
            raise err
        except Exception as err:
            logger.error(f"For {payload_id} Error: {err}")
            raise err

    @staticmethod
    def _mk_query_by_bin_and_duration(
        bin_size: str,
        duration: str,
        event_db_name: Optional[str],
        event_table_name: Optional[str],
    ) -> Optional[str]:
        """bin_size is like '1d' '1h'
        duration is like '356d' '60d'
        """
        if not event_db_name or not event_table_name:
            return None
        else:
            return f"""
                WITH data AS (
                    SELECT BIN(time, {bin_size}) as t, measure_value::varchar as state, item_ids, count(*) as count
                    FROM "{event_db_name}"."{event_table_name}"
                    WHERE measure_name = 'execution_state' AND time BETWEEN ago({duration}) AND now()
                    GROUP BY BIN(time, {bin_size}), measure_value::varchar, item_ids
                    )
                SELECT t, state, count(*) as unique_count, sum(count) as count
                FROM data
                GROUP BY t, state
                ORDER BY t, state
            """

    @staticmethod
    def _mk_hour_query(
        start: int,
        end: int,
        event_db_name: Optional[str],
        event_table_name: Optional[str],
    ) -> Optional[str]:
        if not event_db_name or not event_table_name:
            return None
        else:
            return f"""
                WITH data AS (
                    SELECT ago({start}h) as t, measure_value::varchar as state, item_ids, count(*) as count
                    FROM "{event_db_name}"."{event_table_name}"
                    WHERE measure_name = 'execution_state' AND time BETWEEN ago({start}h) AND ago({end}h)
                    GROUP BY measure_value::varchar, item_ids
                )
                SELECT t, state, count(*) as unique_count, sum(count) as count
                FROM data
                GROUP BY t, state
                ORDER BY t, state
            """

    def _query(self, q: Optional[str]) -> Optional[Dict[str, Any]]:
        return self.tsq_client.query(QueryString=q) if self.enabled() and q else None

    def query_hour(self, start: int, end: int) -> Optional[Dict[str, Any]]:
        return self._query(
            self._mk_hour_query(start, end, self.event_db_name, self.event_table_name)
        )

    def query_by_bin_and_duration(
        self, bin_size: str, duration: str
    ) -> Optional[Dict[str, Any]]:
        return self._query(
            self._mk_query_by_bin_and_duration(
                bin_size, duration, self.event_db_name, self.event_table_name
            )
        )
