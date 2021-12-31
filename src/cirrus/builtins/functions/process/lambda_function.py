import json
import os

from cirrus.lib.process_payload import ProcessPayload, ProcessPayloads
from cirrus.lib.utils import dict_merge
from cirrus.lib.logging import get_task_logger

logger = get_task_logger('lambda_function.process', payload=tuple())

# Default PROCESSES
# TODO: put this configuration into the cirrus.yml
with open(os.path.join(os.path.dirname(__file__), 'processes.json')) as f:
    PROCESSES = json.loads(f.read())


def lambda_handler(event, context):
    logger.debug(json.dumps(event))

    # Read SQS event
    if 'Records' not in event:
        raise ValueError("Input not from SQS")

    # TODO: a large number of input collections will cause a timeout
    # find a way to process each input message, deleting it from the queue
    # any not processed before timeout will be retried on the next execution
    payloads = []
    for record in [json.loads(r['body']) for r in event['Records']]:
        payload = json.loads(record['Message'])
        logger.debug('payload: %s', json.dumps(payload))
        # expand payload_ids to full payloads
        if 'payload_ids' in payload:
            _payloads = ProcessPayloads.from_payload_ids(payload['payload_ids'])
            if 'process_update' in payload:
                logger.debug(
                    "Process update: %s",
                    json.dumps(payload['process_update']),
                )
                for c in _payloads:
                    c['process'] = dict_merge(
                        c['process'],
                        payload['process_update'],
                    )
            payloads = ProcessPayloads(_payloads)
            payloads.process(replace=True)
        elif payload.get('type', '') == 'Feature':
            # If Item, create ProcessPayload and
            # use default process for that collection
            if payload['collection'] not in PROCESSES.keys():
                raise ValueError(
                    "Default process not provided for "
                    f"collection {payload['collection']}",
                )
            payload_json = {
                'type': 'FeatureCollection',
                'features': [payload],
                'process': PROCESSES[payload['collection']]
            }
            payloads.append(ProcessPayload(payload_json, update=True))
        else:
            payloads.append(ProcessPayload(payload, update=True))

    if len(payloads) > 0:
        _payloads = ProcessPayloads(payloads)
        _payloads.process()

    return len(payloads)
