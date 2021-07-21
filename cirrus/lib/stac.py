import boto3
import json
import logging
import os

from boto3utils import s3
from typing import Dict, Optional, List

from pystac import STAC_IO, Catalog, CatalogType, Collection, Link

logger = logging.getLogger(__name__)

# envvars
DATA_BUCKET = os.getenv('CIRRUS_DATA_BUCKET', None)
STAC_VERSION = os.getenv('CIRRUS_STAC_VERSION', '1.0.0-beta.2')
DESCRIPTION = os.getenv('CIRRUS_STAC_DESCRIPTION', 'Cirrus STAC')
AWS_REGION = os.getenv('AWS_REGION')
PUBLISH_TOPIC = os.getenv('CIRRUS_PUBLISH_TOPIC_ARN', None)
PUBLIC_CATALOG = os.getenv('CIRRUS_PUBLIC_CATALOG', False)
if isinstance(PUBLIC_CATALOG, str):
    PUBLIC_CATALOG = True if PUBLIC_CATALOG.lower() == 'true' else False

# root catalog
ROOT_URL = f"s3://{DATA_BUCKET}"
if PUBLIC_CATALOG:
    ROOT_URL = s3.s3_to_https(ROOT_URL, region=AWS_REGION)

# boto3 clients
snsclient = boto3.client('sns')


def s3stac_read(uri):
    if uri.startswith('http'):
        uri = s3.https_to_s3(uri)
    return json.dumps(s3().read_json(uri))

def s3stac_write(uri, txt):
    extra = {
        'ContentType': 'application/json'
    }
    if uri.startswith('http'):
        uri = s3.https_to_s3(uri)
    s3().upload_json(json.loads(txt), uri, extra=extra, public=PUBLIC_CATALOG)

STAC_IO.read_text_method = s3stac_read
STAC_IO.write_text_method = s3stac_write


def get_root_catalog():
    """Get Cirrus root catalog from s3

    Returns:
        Dict: STAC root catalog
    """
    caturl = f"{ROOT_URL}/catalog.json"
    if s3().exists(caturl):
        cat = Catalog.from_file(caturl)
    else:
        catid = DATA_BUCKET.split('-data-')[0]
        cat = Catalog(id=catid, description=DESCRIPTION)
        cat.normalize_and_save(ROOT_URL, CatalogType.ABSOLUTE_PUBLISHED)
    logger.debug(f"Fetched {cat.describe()}")
    return cat


# add this collection to Cirrus catalog
def add_collections(collections, publish=True):

    for collection in collections:
        collection.remove_links('child')
        link = Link('copied_from', collection)
        collection.add_link(link, collection.get_self_href())
        ROOT_CATALOG.add_child(collection)
        if publish:
            child_json = json.dumps(collection.to_dict())
            logger.debug(f"Publishing {collection.id}: {child_json}")
            response = snsclient.publish(TopicArn=PUBLISH_TOPIC, Message=child_json)
            logger.debug(f"SNS Publish response: {json.dumps(response)}")
 
    ROOT_CATALOG.normalize_and_save(ROOT_URL, CatalogType.ABSOLUTE_PUBLISHED)
    return ROOT_CATALOG


ROOT_CATALOG = get_root_catalog()