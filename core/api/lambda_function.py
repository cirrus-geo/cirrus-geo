import boto3
import json
import logging
import os
from urllib.parse import urljoin, urlparse

from cirruslib import StateDB, stac, STATES

logger = logging.getLogger(__name__)

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
    cat_url = urljoin(stac.ROOT_URL, "catalog.json")

    links = []
    for l in cat['links']:
        if l['rel'] == 'child':
            parts = urlparse(l['href'])
            name = parts.path.split('/')[1]
            link = create_link(urljoin(root_url, f"collections/{name}"), name, 'child')
            links.append(link)
    links.insert(0, create_link(root_url, "home", "self"))
    links.append(create_link(cat_url, "STAC", "stac"))

    root = {
        "id": f"{cat['id']}-state-api",
        "description": f"{cat['description']} State API",
        "links": links
    }

    return root


def summary(collections_workflow, since, limit):
    parts = collections_workflow.rsplit('/workflow-', maxsplit=1)
    logger.debug(f"Getting summary for {collections_workflow}")
    counts = {}
    for s in STATES:
        counts[s] = statedb.get_counts(collections_workflow, state=s, since=since, limit=limit)
    return {
        "collections": parts[0],
        "workflow": parts[1],
        "counts": counts
    }


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

    catid = event.get('path', '').rstrip('/').rstrip(stage).rstrip('/')
    logger.info(f"Path parameters: {catid}")

    # get query parameters
    qparams = event['queryStringParameters'] if event.get('queryStringParameters') else {}
    logger.info(f"Query Parameters: {qparams}")
    state = qparams.get('state', None)
    since = qparams.get('since', None)
    nextkey = qparams.get('nextkey', None)
    limit = int(qparams.get('limit', 100))
    count_limit = int(qparams.get('count_limit', 100000))
    legacy = qparams.get('legacy', False)

    # root endpoint
    if catid == '':
        return response(get_root(root_url))

    if '/workflow-' not in catid:
        return response(f"{path} not found", status_code=400)
        
    key = statedb.catid_to_key(catid)

    if key['itemids'] == '':
        # get summary of collection
        return response(summary(catid, since=since, limit=limit))
    elif key['itemids'] == 'items':
        # get items
        logger.debug(f"Getting items for {key['collections_workflow']}, state={state}, since={since}")
        items = statedb.get_items_page(key['collections_workflow'], state=state, since=since,
                                        limit=limit, nextkey=nextkey)
        if legacy:
            legacy_items = []
            for item in items:
                _item = {
                    'catid': item['catid'],
                    'input_collections': item['collections'],
                    'state': item['state'],
                    'created_at': item['created'],
                    'updated_at': item['updated'],
                    'input_catalog': item['catalog']
                }
                if 'executions' in item:
                    _item['execution'] = item['executions'][-1]
                if 'outputs' in item:
                    _item['items'] = item['outputs']
                if 'last_error' in item:
                    _item['error_message'] = item['last_error']
                legacy_items.append(_item)
            items = legacy_items

        return response(items)
    else:
        # get individual item
        resp = statedb.dbitem_to_item(statedb.get_dbitem('/'.join(catid)))
        return response(resp)
