"""Fake workflow event generator.

pip install -r requirements.txt

python fake_workflow_event_generator.py my-cirrus-dev-state-events my-cirrus-dev-state-events-table

First arg is the Timestream DB, second arg is the Timestream table.
"""
import logging
import random
import sys
import uuid
from datetime import datetime, timezone
from enum import Enum, unique
from typing import Dict

import boto3
from dateutil.parser import isoparse
from faker import Faker

logger = logging.getLogger(__name__)


@unique
class StateEnum(Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    ABORTED = "ABORTED"
    TERMINAL = "TERMINAL"


tsw_client = boto3.client("timestream-write", region_name="us-west-2")


def write_timeseries_record(
    event_db_name: str,
    event_table_name: str,
    key: Dict[str, str],
    state: StateEnum,
    event_time: str,
    last_update_ts_str: str,
):
    collections_workflow = key.get("collections_workflow")
    itemids = key.get("itemids")

    if not collections_workflow or not itemids:
        logger.error(
            f"Event could not be recorded, key {key} missing 'collections_workflow' or 'itemids'"
        )
        return

    event_time_dt = datetime.fromisoformat(event_time)
    event_time_ms = str(int(event_time_dt.timestamp() * 1000))

    duration_ms = str(
        int((isoparse(last_update_ts_str) - event_time_dt).microseconds / 1000)
    )

    record = {
        "Dimensions": [
            {"Name": "collections_workflow", "Value": collections_workflow},
            {"Name": "item_ids", "Value": itemids},
            {"Name": "state", "Value": state.value},
        ],
        "MeasureValueType": "BIGINT",
        "Time": event_time_ms,
        "MeasureName": "duration_ms",
        "MeasureValue": duration_ms,
    }

    try:
        result = tsw_client.write_records(
            DatabaseName=event_db_name,
            TableName=event_table_name,
            Records=[record],
        )
        logger.info(
            f"Timestream WriteRecords Status for first time: [{result['ResponseMetadata']['HTTPStatusCode']}]"
        )
    except tsw_client.exceptions.RejectedRecordsException as err:
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


state_transitions = {
    StateEnum.PROCESSING: [
        StateEnum.INVALID,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.COMPLETED,
        StateEnum.FAILED,
        StateEnum.FAILED,
        StateEnum.ABORTED,
    ],
    StateEnum.ABORTED: [
        StateEnum.PROCESSING,
        StateEnum.PROCESSING,
        StateEnum.PROCESSING,
        StateEnum.PROCESSING,
        StateEnum.PROCESSING,
        StateEnum.TERMINAL,
    ],
    StateEnum.FAILED: [
        StateEnum.PROCESSING,
        StateEnum.PROCESSING,
        StateEnum.PROCESSING,
        StateEnum.TERMINAL,
    ],
}

Faker.seed(0)

fake = Faker()


def generate_item_events():
    key = {"collections_workflow": "sentinel-2-l2a", "itemids": str(uuid.uuid4())}
    state = None
    timestamp = fake.date_time_between("-3d")
    last_update_ts = None
    while state not in [StateEnum.COMPLETED, StateEnum.INVALID, StateEnum.TERMINAL]:
        if state is None:
            state = StateEnum.PROCESSING
        else:
            state = random.choice(state_transitions[state])

        yield key, state, timestamp.astimezone(
            timezone.utc
        ).isoformat(), last_update_ts.astimezone(
            timezone.utc
        ).isoformat() if last_update_ts else timestamp.astimezone(
            timezone.utc
        ).isoformat()

        last_update_ts = timestamp
        timestamp = fake.date_time_between(timestamp, "+2h")
        if timestamp > datetime.now():
            timestamp = datetime.now()


def generate_events():
    while True:
        yield from generate_item_events()


def main():
    event_db_name = sys.argv[1]
    event_table_name = sys.argv[2]
    for x in generate_events():
        key, state, timestamp, last_update_ts = x
        print(x)
        write_timeseries_record(
            event_db_name, event_table_name, key, state, timestamp, last_update_ts
        )


if __name__ == "__main__":
    main()
