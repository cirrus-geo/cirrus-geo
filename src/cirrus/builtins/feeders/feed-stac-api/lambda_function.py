import argparse
import boto3
import datetime
import json
import logging
import math
import os
import sys
import time
from copy import deepcopy
from dateutil.parser import parse

from cirrus.lib.utils import submit_batch_job
from satsearch import Search


# envvars
SNS_TOPIC = os.getenv('CIRRUS_PROCESS_TOPIC_ARN')
MAX_ITEMS_REQUEST = 5000

# boto clients
SNS_CLIENT = boto3.client('sns')

# logging
logger = logging.getLogger("feeder.stac-api")


def split_request(params, nbatches):
    dates = params.get('datetime', '').split('/')

    if len(dates) != 2:
        msg = "Do not know how to split up request without daterange"
        logger.error(msg)
        raise Exception(msg)
    start_date = parse(dates[0])
    if dates[1] == "now":
        stop_date = datetime.datetime.now()
    else:
        stop_date = parse(dates[1])
    td = stop_date - start_date
    hours_per_batch = math.ceil(td.total_seconds()/3600/nbatches)
    ranges = []
    for i in range(0, nbatches-1):
        dt1 = start_date + datetime.timedelta(hours=hours_per_batch*i)
        dt2 = dt1 + datetime.timedelta(hours=hours_per_batch) - datetime.timedelta(seconds=1)
        ranges.append([dt1, dt2])
    # insert last one
    ranges.append([
        ranges[-1][1] + datetime.timedelta(seconds=1),
        stop_date
    ])

    for r in ranges:
        request = deepcopy(params)
        request["datetime"] = f"{r[0].strftime('%Y-%m-%dT%H:%M:%S')}/{r[1].strftime('%Y-%m-%dT%H:%M:%S')}"
        logger.debug(f"Split date range: {request['datetime']}")
        yield request


def run(params, url, sleep=None, process=None):
    search = Search(url=url, **params)
    logger.debug(f"Searching {url}")
    found = search.found()
    logger.debug(f"Total items found: {found}")

    if found < MAX_ITEMS_REQUEST:
        logger.info(f"Making single request for {found} items")
        items = search.items()
        for i, item in enumerate(items):
            payload = {
                'type': 'FeatureCollection',
                'features': [item._data]
            }
            if process:
                payload['process'] = process
            resp = SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Message=json.dumps(payload))
            if (i % 500) == 0:
                logger.debug(f"Added {i+1} items to Cirrus")
            #if resp['StatusCode'] != 200:
            #    raise Exception("Unable to publish")
            if sleep:
                time.sleep(sleep)
        logger.debug(f"Published {len(items)} items to {SNS_TOPIC}")
    else:
        # bisection
        nbatches = 2
        logger.info(f"Too many Items for single request, splitting into {nbatches} batches by date range")
        for params in split_request(params, nbatches):
            run(params, url, process=process)


def lambda_handler(event, context={}):
    logger.debug('Event: %s' % json.dumps(event))

    url = event.get('url')
    params = event.get('search', {})
    max_items_batch = event.get('max_items_batch', 15000)
    sleep = event.get('sleep', None)
    process = event.get('process', None)

    # search API
    search = Search(url=url, **params)
    logger.debug(f"Searching {url}")

    found = search.found()
    logger.debug(f"Total items found: {found}")

    if found <= MAX_ITEMS_REQUEST:
        return run(params, url, sleep=sleep, process=process)
    elif hasattr(context, "invoked_function_arn"):
        nbatches = int(found / max_items_batch) + 1
        if nbatches == 1:
            submit_batch_job(event, context.invoked_function_arn, definition='lambda-as-batch')
        else:
            for request in split_request(params, nbatches):
                event['search'] = request
                submit_batch_job(event, context.invoked_function_arn, definition='lambda-as-batch')
        logger.info(f"Submitted {nbatches} batches")
        return
    else:
        run(params, url, sleep=sleep, process=process)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # argparse
    parser = argparse.ArgumentParser(description='feeder')
    parser.add_argument('payload', help='Payload file')
    args = parser.parse_args(sys.argv[1:])

    with open(args.payload) as f:
        payload = json.loads(f.read())
    lambda_handler(payload)
