# ruff: noqa
"""Fake workflow event generator.

pip install -r requirements.txt

python fake_workflow_event_generator.py my-cirrus-dev-state-events my-cirrus-dev-state-events-table -60d

First arg is the Timestream DB, second arg is the Timestream table, third is the time duration expression.

Write to Magnetic store must be enabled manually for this to work.
"""

import logging
import random
import sys
import uuid

from datetime import UTC, datetime
from enum import Enum, unique

import boto3

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
    execution_arn: str,
):
    record = {
        "Dimensions": [
            {"Name": "workflow", "Value": workflow},
            {"Name": "collections", "Value": collections},
            {"Name": "item_ids", "Value": itemids},
            {"Name": "execution_arn", "Value": execution_arn},
        ],
        "Time": str(int(datetime.fromisoformat(event_time).timestamp() * 1000)),
        "MeasureValueType": "VARCHAR",
        "MeasureName": "state",
        "MeasureValue": state.value,
    }

    try:
        result = tsw_client.write_records(
            DatabaseName=event_db_name,
            TableName=event_table_name,
            Records=[record],
        )
        logger.info(
            f"Timestream WriteRecords Status for first time: [{result['ResponseMetadata']['HTTPStatusCode']}]",
        )
    except tsw_client.exceptions.RejectedRecordsException as err:
        logger.error(f"Timestream RejectedRecords: {err}")
        for rr in err.response["RejectedRecords"]:
            logger.error(f"Rejected Index {rr['RecordIndex']} : {rr['Reason']}")
            if "ExistingVersion" in rr:
                logger.error(
                    f"Rejected record existing version: {rr['ExistingVersion']}",
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

fake = Faker()


def generate_item_events(between_val: str):
    state = None
    timestamp = fake.date_time_between(between_val)
    execution_arn = f"arn:aws:states:us-west-2:1667831315:execution:pvarner-cirrus-dev-fake:{uuid.uuid4()!s}"

    while state not in [StateEnum.COMPLETED, StateEnum.INVALID, StateEnum.TERMINAL]:
        if state is None:
            state = StateEnum.PROCESSING
        else:
            state = random.choice(state_transitions[state])

        if state != StateEnum.TERMINAL:
            yield (
                "workflow1",
                "sentinel-2-l2a",
                str(
                    uuid.uuid4(),
                ),
                state,
                timestamp.astimezone(UTC).isoformat(),
                execution_arn,
            )

            timestamp = fake.date_time_between(timestamp, "+2h")
            if timestamp > datetime.now():
                timestamp = datetime.now()


def generate_events(between_val: str):
    while True:
        yield from generate_item_events(between_val)


def main():
    event_db_name = sys.argv[1]
    event_table_name = sys.argv[2]
    between_val = sys.argv[3]
    for event in generate_events(between_val):
        print(event)
        write_timeseries_record(event_db_name, event_table_name, *event)


if __name__ == "__main__":
    main()
