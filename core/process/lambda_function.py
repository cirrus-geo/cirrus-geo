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

    catalogs = []
    
    # Read SQS payload
    if 'Records' not in payload:
        raise ValueError("Input not from SQS")
    for catalog in [json.loads(r['body']) for r in payload['Records']]:
        catalogs.append(catalog)

    # Make sure FeatureCollection, and Process block included
    cats = []
    for catalog in catalogs:
        logger.debug(f"Catalog: {json.dumps(catalog)}")

        # existing catalog IDs provided, rerun these
        if 'catids' in catalog:
            catalogs = Catalogs.from_catids(catalog['catids'])
            catalogs.process(replace=True)
            continue

        # If Item, create Catalog using default process for that collection
        if catalog.get('type', '') == 'Feature':
            if catalog['collection'] not in PROCESSES.keys():
                raise ValueError(f"Default process not provided for collection {catalog['collection']}")
            cat_json = {
                'type': 'FeatureCollection',
                'features': [catalog],
                'process': PROCESSES[catalog['collection']]
            }
        else:
            # otherwise, treat as input catalog
            cat_json = catalog
            if 'process' not in cat_json:
                cat_json['process'] = PROCESSES[cat_json['collection']]

        # create Catalog instance, update/add fields as needed (e.g., id)
        cat = Catalog(cat_json, update=True)
        cats.append(cat)

    if len(cats) > 0:
        catalogs = Catalogs(cats)
        catalogs.process()
