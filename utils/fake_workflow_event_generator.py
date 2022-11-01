"""Fake workflow event generator.

pip install -r requirements.txt

python fake_workflow_event_generator.py my-cirrus-dev-state-events my-cirrus-dev-state-events-table

First arg is the Timestream DB, second arg is the Timestream table.

Write to Magnetic store must be enabled manually for this to work.
"""
import logging
import random
import sys
import uuid
from datetime import datetime, timezone
from enum import Enum, unique
from typing import Optional

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
    workflow: str,
    collections: str,
    itemids: str,
    state: StateEnum,
    event_time: str,
    last_update_ts_str: Optional[str],
):
    event_time_dt = datetime.fromisoformat(event_time)
    event_time_ms = str(int(event_time_dt.timestamp() * 1000))

    duration_ms = (
        str((event_time_dt - isoparse(last_update_ts_str)).seconds * 1000)
        if last_update_ts_str
        else "0"
    )

    print(last_update_ts_str)
    print(event_time_dt)
    print(duration_ms)

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
        result = tsw_client.write_records(
            DatabaseName=event_db_name,
            TableName=event_table_name,
            Records=[record],
        )
        logger.info(
            f"Timestream WriteRecords Status for first time: [{result['ResponseMetadata']['HTTPStatusCode']}]"
        )
    except Exception as err:
        logger.error(f"Error: {err}")


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
    state = None
    timestamp = fake.date_time_between("-3d")
    last_update_ts = None
    while state not in [StateEnum.COMPLETED, StateEnum.INVALID, StateEnum.TERMINAL]:
        if state is None:
            state = StateEnum.PROCESSING
        else:
            state = random.choice(state_transitions[state])

        if state != StateEnum.TERMINAL:
            yield "workflow1", "sentinel-2-l2a", str(
                uuid.uuid4()
            ), state, timestamp.astimezone(
                timezone.utc
            ).isoformat(), last_update_ts.astimezone(
                timezone.utc
            ).isoformat() if last_update_ts else None

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
    for (
        workflow,
        collection,
        itemids,
        state,
        timestamp,
        last_update_ts,
    ) in generate_events():
        print(
            f"{workflow}, {collection}, {itemids}, {state}, {timestamp}, {last_update_ts}"
        )
        write_timeseries_record(
            event_db_name,
            event_table_name,
            workflow,
            collection,
            itemids,
            state,
            timestamp,
            last_update_ts,
        )


if __name__ == "__main__":
    main()
