#!/usr/bin/env python
import boto3
import json
import logging
import requests

from boto3 import Session
from boto3utils import s3
from cirruslib import Catalogs
from cirruslib.errors import InvalidInput
from os import getenv, environ, path as op
from stac_sentinel import sentinel_s2_l1c, sentinel_s2_l2a
from shutil import rmtree
from tempfile import mkdtemp
from traceback import format_exc
from urllib.parse import urlparse

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))
logger.addHandler(logging.StreamHandler())

DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET')


def lambda_handler(payload, context={}):
    logger.debug('Payload: %s' % json.dumps(payload))

    catalog = Catalogs.from_payload(payload)[0]

    # TODO - make this more general for more items/collections
    assert(len(catalog['features']) == 1)

    # configuration options
    #config = catalog['process']['functions'].get('sentinel-to-stac', {})
    #output_options = catalog['process'].get('output_options', {})
    #output_credentials = output_options.get('credentials', {})

    # this process assumes single output collection, as it's just converting from original Sentinel to STAC for 1 scene
    output_collection = catalog['process']['output_options']['collections'].keys()[0]

    items = []
    # get metadata
    url = catalog['features'][0]['assets']['tileInfo']['href'].rstrip()
    # if this is the FREE URL, get s3 base
    if url[0:5] == 'https':
        base_url = 's3:/' + op.dirname(urlparse(url).path)
    else:
        base_url = op.dirname(url)

    # get metadata
    resp = requests.get(url, stream=True)
    if resp.status_code != 200:
        msg = f"sentinel-to-stac: failed fetching {url} for {catalog['id']} ({resp.text})"
        logger.error(msg)
        logger.error(format_exc())
        raise InvalidInput(msg)
    metadata = json.loads(resp.text)

    # if sentinel-s2-l2a we need to get cloud cover from sentinel-s2-l1c
    # so go ahead and publish that one as well
    if output_collection == 'sentinel-s2-l2a':
        _url = url.replace('sentinel-s2-l2a', 'sentinel-s2-l1c')
        resp = requests.get(_url, stream=True)
        l1c_present = False
        if resp.status_code != 200:
            msg = f"sentinel-to-stac: failed fetching {_url} for {catalog['id']} ({resp.text})"
            logger.error(msg)
        else:
            l1c_present = True
            logger.debug(f"sentinel-s2-l1c request response: {resp}")
            _metadata = json.loads(resp.text)
            _item = sentinel_s2_l1c(_metadata, base_url.replace('sentinel-s2-l2a', 'sentinel-s2-l1c'))
            for a in ['thumbnail', 'info', 'metadata']:
                _item['assets'][a]['href'] = _item['assets'][a]['href'].replace('s3:/', 'https://roda.sentinel-hub.com')
            # if dataCoveragePercentage not in L1 data, try getting from L2
            if 'dataCoveragePercentage' not in _metadata and 'dataCoveragePercentage' in metadata:
                _item['properties']['sentinel:data_coverage'] = float(metadata['dataCoveragePercentage'])
            items.append(_item)
            metadata['cloudyPixelPercentage'] = _metadata['cloudyPixelPercentage']
            if 'tileDataGeometry' not in metadata and 'tileDataGeometry' in _metadata:
                metadata['tileDataGeometry'] = _metadata['tileDataGeometry']

    try:
        item = sentinel_s2_l2a(metadata, base_url)
        for a in ['thumbnail', 'info', 'metadata']:
            item['assets'][a]['href'] = item['assets'][a]['href'].replace('s3:/', 'https://roda.sentinel-hub.com')

        if l1c_present:
            item['properties']['sentinel:valid_cloud_cover'] = True
        else:
            item['properties']['sentinel:valid_cloud_cover'] = False

        # discard if crossing antimeridian
        if item['bbox'][2] - item['bbox'][0] > 300:
            msg = f"{item['id']} crosses antimeridian, discarding"
            logger.error(msg)
            raise InvalidInput(msg)
        
        items.append(item)

        # update STAC catalog
        catalog['collections'] = []
        catalog['features'] = items
        logger.debug(f"STAC Output: {json.dumps(catalog)}")
    except Exception as err:
        msg = f"sentinel-to-stac: failed processing {catalog['id']} ({err})"
        logger.error(msg)
        logger.error(format_exc())
        raise Exception(msg)

    return catalog
