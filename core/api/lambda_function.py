import boto3
import json
import logging
import os
from urllib.parse import urljoin, urlparse

from cirruslib import StateDB, stac

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

# Cirrus state database
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
    cat = stac.ROOT_CATALOG.to_dict()

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
    cat['links'].insert(0, create_link(root_url, "home", "self"))

    cat_url = urljoin(stac.ROOT_URL, "catalog.json")
    cat['links'].append(create_link(cat_url, "STAC", "stac"))

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

    # get path parameters
    stage = event.get('requestContext', {}).get('stage', '')
    path = event.get('path', '').split('/')
    pparams = [p for p in path if p != '' and p != stage]
    logger.info(f"Path Parameters: {pparams}")

    # get query parameters
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

        # get single item by catalog ID (deprecated)
        if pparams[0] == "item" and len(pparams) > 1:
            catid = '/'.join(pparams[1:])
            return response(statedb.get_dbitem(catid))
        # determine index (input or output collections)
        if pparams[0] == 'catid':
            resp = statedb.dbitem_to_item(statedb.get_dbitem('/'.join(pparams[1:])))
            return response(resp)
        elif pparams[0] == 'collections':
            index = 'input_state'
            # get items
            if pparams[-1] == 'items' and len(pparams) > 2:
                colid = '/'.join(pparams[1:-1])
                logger.debug(f"Getting items from {index} for collections {colid}, state={state}, since={since}")
                resp = statedb.get_items_page(colid, state=state, since=since, index=index,
                                            limit=limit, nextkey=nextkey)
                return response(resp)
        
            # get summary of collection
            if len(pparams) > 1:
                colid = '/'.join(pparams[1:])
                logger.debug(f"Getting summary from {index} for collection {colid}")
                counts = statedb.get_counts(colid, state=state, since=since, index=index, limit=100000)
                return response(counts)

    except Exception as err:
        msg = f"api failed: {err}"
        logger.error(msg, exc_info=True)
        return response(msg, status_code=400)
