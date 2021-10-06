import json
import os

from cirruslib import Catalog, Catalogs
from cirruslib.utils import dict_merge
from cirruslib.logging import get_task_logger


logger = get_task_logger('lambda_function.process', catalog=tuple())

# Default PROCESSES
# TODO: put this configuration into the cirrus.yml
with open(os.path.join(os.path.dirname(__file__), 'processes.json')) as f:
    PROCESSES = json.loads(f.read())


def lambda_handler(payload, context):
    logger.debug(json.dumps(payload))

    # Read SQS payload
    if 'Records' not in payload:
        raise ValueError("Input not from SQS")

    # TODO: a large number of input collections will cause a timeout
    # find a way to process each input message, deleting it from the queue
    # any not processed before timeout will be retried on the next execution
    catalogs = []
    for record in [json.loads(r['body']) for r in payload['Records']]:
        cat = json.loads(record['Message'])
        logger.debug('cat: %s' % json.dumps(cat))
        # expand catids to full catalogs
        if 'catids' in cat:
            _cats = Catalogs.from_catids(cat['catids'])
            if 'process_update' in cat:
                logger.debug("Process update: %s", json.dumps(cat['process_update']))
                for c in _cats:
                    c['process'] = dict_merge(c['process'], cat['process_update'])
            cats = Catalogs(_cats)
            cats.process(replace=True)
        elif cat.get('type', '') == 'Feature':
            # If Item, create Catalog and use default process for that collection
            if cat['collection'] not in PROCESSES.keys():
                raise ValueError(
                    f"Default process not provided for collection {cat['collection']}",
                )
            cat_json = {
                'type': 'FeatureCollection',
                'features': [cat],
                'process': PROCESSES[cat['collection']]
            }
            catalogs.append(Catalog(cat_json, update=True))
        else:
            catalogs.append(Catalog(cat, update=True))

    if len(catalogs) > 0:
        cats = Catalogs(catalogs)
        cats.process()

    return len(catalogs)
