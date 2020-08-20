import boto3
import json
import logging
import os

from boto3utils import s3
from cirruslib import Catalog, Catalogs
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(os.getenv('CIRRUS_LOG_LEVEL', 'INFO'))


# Default PROCESSES
with open(os.path.join(os.path.dirname(__file__), 'processes.json')) as f:
    PROCESSES = json.loads(f.read())


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    payloads = []
    
    if 'Records' in payload:
        for record in [json.loads(r['body']) for r in payload['Records']]:
            if 'Message' in record:
                # SNS
                payloads.append(json.loads(record['Message']))
            else:
                # SQS
                payloads.append(record)
    else:
        payloads = [payload]

    cats = []
    for p in payloads:
        logger.debug(f"Payload: {json.dumps(p)}")
        # If Item, create Catalog using default process for that collection
        if p['type'] == 'Feature':
            if p['collection'] not in PROCESSES.keys():
                raise Exception(f"Default process not provided for collection {p['collection']}")
            cat = Catalog({
                'type': 'FeatureCollection',
                'features': [p],
                'process': PROCESSES[p['collection']]
            })
            cats.append(cat)
        else:
            if 'process' not in p:
                p['process'] = PROCESSES[p['collection']]
            cats.append(Catalog(p))

    catalogs = Catalogs(cats)
    catids = catalogs.process()

    return catids
