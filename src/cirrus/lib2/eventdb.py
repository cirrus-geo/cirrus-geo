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
        event_db_and_table_names: Optional[str] = None,
        session: Optional[boto3.Session] = None,
    ):
        if not session:
            session = boto3.Session()

        self.tsw_client = session.client("timestream-write")
        self.tsq_client = session.client("timestream-query")

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

    def write_timeseries_record(
        self,
        key: Dict[str, str],
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled():
            return None

        parts = key.get("collections_workflow", "").rsplit("_", 1)
        if not len(parts) == 2:
            logger.error(
                f"Event could not be recorded, key value collections_workflow was not an underscore-separated value: {key.get('collections_workflow')}"
            )
            raise ValueError(
                "In key dict, value for collections_workflow was not an underscore-separated string"
            )

        collections = parts[0]
        workflow = parts[1]

        itemids = key.get("itemids")

        if not all((collections, workflow, itemids)):
            logger.error(
                f"Event could not be recorded, key {key} missing values to populate 'workflow', 'collections' or 'itemids'"
            )
            raise ValueError(
                "At least one of 'workflow', 'collections' or 'itemids' could not be determined from key"
            )

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
            logger.error(f"For {key} Timestream RejectedRecords: {err}")
            for rr in err.response["RejectedRecords"]:
                logger.error(
                    f"For {key} Rejected Index {rr['RecordIndex']} : {rr['Reason']}"
                )
                if "ExistingVersion" in rr:
                    logger.error(
                        f"For {key} Rejected record existing version: {rr['ExistingVersion']}"
                    )
            raise err
        except Exception as err:
            logger.error(f"For {key} Error: {err}")
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
