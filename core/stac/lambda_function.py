import boto3
import json
import logging
import requests
import sys

from boto3utils import s3
from boto3.dynamodb.conditions import Key
#from cirruslib  import stac
from json import dumps
from os import getenv, path as op
from shutil import rmtree
from tempfile import mkdtemp
from traceback import format_exc
from urllib.parse import urljoin

from pystac import STAC_IO, Catalog, CatalogType, Collection, Link


# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

# envvars
DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET', None)
PUBLIC_CATALOG = getenv('CIRRUS_PUBLIC_CATALOG', False)
STAC_VERSION = getenv('CIRRUS_STAC_VERSION', '1.0.0-beta.2')
DESCRIPTION = getenv('CIRRUS_STAC_DESCRIPTION', 'Cirrus STAC')
PUBLISH_TOPIC = getenv('CIRRUS_PUBLISH_TOPIC_ARN', None)

REGION = getenv('AWS_REGION', 'us-west-2')
CONSOLE_URL = f"https://{REGION}.console.aws.amazon.com/"

snsclient = boto3.client('sns')


ROOT_URL = f"s3://{DATA_BUCKET}"
PUBLIC_ROOT_URL = s3.s3_to_https(ROOT_URL, region=REGION)


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
        if PUBLIC_CATALOG:
            cat.normalize_and_save(PUBLIC_ROOT_URL, CatalogType.ABSOLUTE_PUBLISHED)
        else:
            cat.normalize_and_save(ROOT_URL, CatalogType.ABSOLUTE_PUBLISHED)
    logger.debug(f"Fetched {cat.describe()}")
    return cat


def lambda_handler(event, context={}):
    logger.debug('Event: %s' % json.dumps(event))

    root_cat = get_root_catalog()

    # check if collection and if so, add to Cirrus
    if 'extent' in event:
        # add to static catalog
        col = Collection.from_dict(event)
        root_cat.add_child(col)

        # send to Cirrus Publish SNS
        response = snsclient.publish(TopicArn=PUBLISH_TOPIC, Message=json.dumps(col.to_dict()))
        logger.debug(f"SNS Publish response: {json.dumps(response)}")

    # check if URL to catalog
    if 'catalog_url' in event:
        cat = Catalog.from_file(event['catalog_url'])

        for child in cat.get_children():
            if isinstance(child, Collection):
                child.remove_links('child')
                link = Link('copied_from', child)
                child.add_link(link, child.get_self_href())
                root_cat.add_child(child)
                child_json = json.dumps(child.to_dict())
                logger.debug(f"Publishing {child.id}: {child_json}")
                response = snsclient.publish(TopicArn=PUBLISH_TOPIC, Message=child_json)
                logger.debug(f"SNS Publish response: {json.dumps(response)}")

    if PUBLIC_CATALOG:
        cat.normalize_and_save(PUBLIC_ROOT_URL, CatalogType.ABSOLUTE_PUBLISHED)
    else:
        cat.normalize_and_save(ROOT_URL, CatalogType.ABSOLUTE_PUBLISHED)


if __name__ == "__main__":
    #logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    print('fred')
    payload = {}
    #lambda_handler(payload)