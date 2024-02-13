import argparse
import json
import logging
import sys
from os import getenv

from cirrus.lib2.logging import defer, get_task_logger
from cirrus.lib2.statedb import StateDB
from cirrus.lib2.utils import SQSPublisher, submit_batch_job

logger = get_task_logger("feeder.rerun", payload=tuple())

# envvars
QUEUE_URL = getenv("CIRRUS_PROCESS_QUEUE_URL")

# Cirrus state DB
statedb = StateDB()


def submit(payload_ids):
    with SQSPublisher.get_handler(QUEUE_URL) as handler:
        for payload_id in payload_ids:
            handler.add(json.dumps({"url": StateDB.payload_id_to_url(payload_id)}))


def lambda_handler(payload, context={}):
    logger.debug("Payload: %s", defer(json.dumps, payload, indent=2))

    collections = payload.get("collections")
    workflow = payload.get("workflow")
    state = payload.get("state", None)
    since = payload.get("since", None)
    limit = payload.get("limit", None)
    batch = payload.get("batch", False)
    error_begins_with = payload.get("error_begins_with", None)

    # if this is a lambda and batch is set
    if batch and hasattr(context, "invoked_function_arn"):
        submit_batch_job(payload, context.invoked_function_arn, name="rerun")
        return

    items = statedb.get_items(
        f"{collections}_{workflow}",
        state=state,
        since=since,
        limit=limit,
        error_begins_with=error_begins_with,
    )

    nitems = len(items)
    logger.debug(f"Rerunning {nitems} payloads")

    submit(item["payload_id"] for item in items)

    return {"found": nitems}


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # argparse
    parser = argparse.ArgumentParser(description="feeder")
    parser.add_argument("payload", help="Payload file")
    args = parser.parse_args(sys.argv[1:])

    with open(args.payload) as f:
        payload = json.loads(f.read())
    lambda_handler(payload)
