import boto3
import json
import logging
import requests

from boto3utils import s3
from boto3.dynamodb.conditions import Key
from cirruslib.statedb import StateDB
from json import dumps
from os import getenv, path as op
from shutil import rmtree
from tempfile import mkdtemp
from traceback import format_exc
from urllib.parse import urljoin, urlparse

db = boto3.resource('dynamodb')

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

# envvars
DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET', None)


'''
Endpoints:

/

'''

PROJECT_HOME = getenv('CIRRUS_PROJECT_HOME')
STAC_API_URL = getenv('STAC_API_URL')

statedb = StateDB()


def response(body, status_code=200, headers={}):
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body)
    }


def create_link(url, title, rel, media_type='application/json'):
    return {
        "title": title,
        "rel": rel,
        "type": media_type,
        "href": url
    }


def get_root(root_url):
    caturl = f"s3://{DATA_BUCKET}/catalog.json"
    cat = s3().read_json(caturl)

    #for l in cat['links']:
    #    if l['rel'] in ['self', 'root', 'child']:

    cat['id'] = f"{cat['id']}-state-api"
    cat['description'] = f"{cat['description']} State API"

    links = []
    for l in cat['links']:
        if l['rel'] == 'child':
            parts = urlparse(l['href'])
            name = parts.path.split('/')[1]
            link = create_link(urljoin(root_url, f"collections/{name}"), name, 'child')
            links.append(link)
    
    cat['links'] = links
    cat['links'].insert(0, create_link(root_url, "Home", "self"))

    return cat


def lambda_handler(event, context):
    logger.debug('Event: %s' % json.dumps(event))
    
    # get request URL
    domain = event.get('requestContext', {}).get('domainName', '')
    if domain != '':
        path = event.get('requestContext', {}).get('path', '')
        root_url = f"https://{domain}{path}/"
    else:
        root_url = None

    # get request path
    path = event.get('path', '').split('/')
    pparams = [p for p in path if p != '']
    logger.info(f"Path Parameters: {pparams}")

    qparams = event['queryStringParameters'] if event.get('queryStringParameters') else {}
    logger.info(f"Query Parameters: {qparams}")
    state = qparams.get('state', None)
    since = qparams.get('since', None)
    nextkey = qparams.get('nextkey', None)
    limit = int(qparams.get('limit', 100))

    try:
        # root endpoint
        if len(pparams) == 0:
            return response(get_root(root_url))

        # get single item by catalog ID
        if pparams[0] == "item" and len(pparams) > 1:
            catid = '/'.join(pparams[1:])
            return response(statedb.get_dbitem(catid))

        # determine index (input or output collections)
        index = None
        if pparams[0] == 'collections':
            index = 'input_state'
        elif pparams[0] == 'output_collections':
            index = 'output_state'

        # get items
        if index and pparams[-1] == 'items' and len(pparams) > 2:
            colid = '/'.join(pparams[1:-1])
            logger.debug(f"Getting items from {index} for collections {colid}, state={state}, since={since}")
            resp = statedb.get_items_page(colid, state=state, since=since, index=index,
                                          limit=limit, nextkey=nextkey)
            return response(resp)
    
        # get summary of collection
        if index and len(pparams) > 1:
            colid = '/'.join(pparams[1:])
            logger.debug(f"Getting summary from {index} for collection {colid}")
            counts = statedb.get_counts(colid, state=state, since=since, index=index, limit=100000)
            #counts['total_published'] = stac_item_count(colid)
            return response(counts)

    except Exception as err:
        msg = f"api failed: {err}"
        logger.error(err)
        logger.error(format_exc())
        msg = {
            'path': path,
            'query': qparams
        }
        return response(msg, status_code=400)


def stac_item_count(colid):
    resp = requests.get(f"{STAC_API_URL}/collections/{colid}/items?limit=0")
    logger.debug(f"STAC API response for {colid} items: {resp.json()}")
    return resp.json()['context']['matched']
