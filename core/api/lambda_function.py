import boto3
import json
import logging
import os
from urllib.parse import urljoin, urlparse

from cirruslib import StateDB, stac

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
    count_limit = int(qparams.get('count_limit', 100000))
    legacy = qparams.get('legacy', False)

    try:
        # root endpoint
        if len(pparams) == 0:
            return response(get_root(root_url))

        # determine index (input or output collections)
        if pparams[0] == 'catid':
            resp = statedb.dbitem_to_item(statedb.get_dbitem('/'.join(pparams[1:])))
            return response(resp)
        elif pparams[0] == 'collections':
            # get items
            if pparams[-1] == 'items' and len(pparams) > 2:
                colid = '/'.join(pparams[1:-1])
                logger.debug(f"Getting items for {colid}, state={state}, since={since}")
                items = statedb.get_items_page(colid, state=state, since=since,
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
            elif len(pparams) > 1:
                # get summary of collection
                collection = '/'.join(pparams[1:])
                logger.debug(f"Getting summary for {collection}")
                counts = statedb.get_counts(collection, state=state, since=since, limit=count_limit)
                return response(counts)

    except Exception as err:
        msg = f"api failed: {err}"
        logger.error(msg, exc_info=True)
        return response(msg, status_code=400)
