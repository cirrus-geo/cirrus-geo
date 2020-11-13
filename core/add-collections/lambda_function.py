import json
import logging
import os
import sys

from cirruslib  import stac
from pystac import Catalog, Collection


# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)


def lambda_handler(event, context={}):
    logger.debug('Event: %s' % json.dumps(event))

    # check if collection and if so, add to Cirrus
    if 'extent' in event:
        stac.add_collections([Collection.from_dict(event)])

    # check if URL to catalog - ingest all collections
    if 'catalog_url' in event:
        collections = []
        cat = Catalog.from_file(event['catalog_url'])
        for child in cat.get_children():
            if isinstance(child, Collection):
                collections.append(child)
        stac.add_collections(collections)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    payload = {}
    lambda_handler(payload)