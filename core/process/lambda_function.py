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

    # Make sure FeatureCollection, and Process block included
    cats = []
    for record in records:
        logger.debug(f"Record: {json.dumps(record)}")
        if 'catids' in record:
            catalogs = Catalogs.from_catids(record['catids'])
            catalogs.process(replace=True)
            continue
        # If Item, create Catalog using default process for that collection
        if record.get('type', '') == 'Feature':
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
        # create Catalog instance, update/add fields as needed (e.g., id)
        cat = Catalog(cat_json, update=True)
        cats.append(cat)

    if len(cats) > 0:
        catalogs = Catalogs(cats)
        catalogs.process()

    #return catids
