import json
import logging
import os

from cirruslib import Catalog, Catalogs

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(os.getenv('CIRRUS_LOG_LEVEL', 'INFO'))

# Default PROCESSES
with open(os.path.join(os.path.dirname(__file__), 'processes.json')) as f:
    PROCESSES = json.loads(f.read())


def lambda_handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    records = []
    
    # TODO - should be SQS only
    if 'Records' in payload:
        for record in [json.loads(r['body']) for r in payload['Records']]:
            if 'Message' in record:
                # SNS
                records.append(json.loads(record['Message']))
            else:
                # SQS
                records.append(record)
    else:
        records = [payload]

    cats = []
    for record in records:
        logger.debug(f"Record: {json.dumps(record)}")
        # If Item, create Catalog using default process for that collection
        if record['type'] == 'Feature':
            if record['collection'] not in PROCESSES.keys():
                raise Exception(f"Default process not provided for collection {record['collection']}")
            cat_json = {
                'type': 'FeatureCollection',
                'features': [record],
                'process': PROCESSES[record['collection']]
            }
        else:
            cat_json = record
            if 'process' not in cat_json:
                cat_json['process'] = PROCESSES[cat_json['collection']]
        cat = Catalog(cat_json, update=True)
        cats.append(cat)

    catalogs = Catalogs(cats)

    # check current states and process
    catids = []
    states = catalogs.get_states()
    for cat in catalogs:
        state = states.get(cat['id'], '')
        replace = cat['process'].get('replace', False)
        if state in ['FAILED', ''] or replace:
            catids.append(cat.process())
        else:
            logger.info(f"Skipping {cat['id']}, in {state} state")
            continue

    return catids
