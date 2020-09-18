#!/usr/bin/env python
import boto3
import json
import logging
import pystac
import requests
import landsat

from boto3 import Session
from boto3utils import s3
from cirruslib import Catalogs
from cirruslib.errors import InvalidInput
from dateutil.parser import parse
from os import getenv, environ, path as op
from shutil import rmtree
from tempfile import mkdtemp
from traceback import format_exc
from urllib.parse import urlparse

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'DEBUG'))

DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET')


def fetch_url_as_text(url):
    resp = requests.get(url, stream=True)
    if resp.status_code != 200:
        msg = f"landsat-to-stac: failed fetching {url}: {resp.text}"
        logger.error(msg)
        logger.error(format_exc())
        raise InvalidInput(msg)
    return resp.text


def lambda_handler(payload, context={}):
    logger.debug('Payload: %s' % json.dumps(payload))

    catalog = Catalogs.from_payload(payload)[0]

    # TODO - make this more general for more items/collections
    assert(len(catalog['features']) == 1)

    # configuration options
    #config = catalog['process']['functions'].get('landsat-to-stac', {})
    #output_options = catalog['process'].get('output_options', {})
    #output_credentials = output_options.get('credentials', {})

    # this process assumes single output collection, as it's just converting from original Sentinel to STAC for 1 scene
    #output_collection = list(catalog['process']['output_options']['collections'].keys())[0]
    #output_collection = 'landsat-c1-l2a'

    items = []
    # get metadata
    url = s3().s3_to_https(catalog['features'][0]['assets']['txt']['href'].rstrip())
    base_url = url.rstrip('_MTL.txt')

    # get metadata and convert to JSON
    metadata = landsat.mtl_to_json(fetch_url_as_text(url))

    # get ANG metadata, used for geometry
    ang_text = fetch_url_as_text(base_url + '_ANG.txt')

    bbox = landsat.get_bbox(metadata)

    try:
        item = pystac.Item(
            id = metadata['LANDSAT_PRODUCT_ID'],
            datetime = landsat.get_datetime(metadata),
            bbox = bbox,
            geometry = landsat.get_geometry(ang_text, bbox),
            properties={}
        )

        # add common metadata
        item.common_metadata.gsd = 30.0
        item.common_metadata.platform = metadata['SPACECRAFT_ID']
        item.common_metadata.instruments = metadata['SENSOR_ID'].split('_')

        # add EO extension
        item.ext.enable('eo')
        item.ext.eo.cloud_cover = float(metadata['CLOUD_COVER'])

        # add proj extension
        item.ext.enable('projection')
        item.ext.projection.epsg = landsat.get_epsg(metadata, item.bbox[1], item.bbox[3])

        item.ext.enable('view')
        view_info = landsat.get_view_info(metadata)
        item.ext.view.sun_azimuth = view_info['sun_azimuth']
        item.ext.view.sun_elevation = view_info['sun_elevation']
        item.ext.view.off_nadir = abs(view_info['off_nadir'])

        # collection 2
        #item.ext.enable('scientific')
        #item.ext.sci.doi = metadata['DIGITAL_OBJECT_IDENTIFIER']

        item.ext.enable('landsat')
        item.ext.landsat.apply(**landsat.get_landsat_info(metadata))
        #item.ext.landsat

        landsat.add_assets(item, base_url)

        #item.validate()
        items.append(item.to_dict())

    except Exception as err:
        msg = f"landsat-to-stac: failed creating STAC for {catalog['id']} ({err})"
        logger.error(msg)
        logger.error(format_exc())
        raise Exception(msg)

    # discard if crossing antimeridian
    logger.debug(f"bbox = {item.bbox}")
    if item.bbox[2] - item.bbox[0] > 300:
        msg = f"{item['id']} crosses antimeridian, discarding"
        logger.error(msg)
        raise InvalidInput(msg)

    # update STAC catalog
    catalog['features'] = items
    logger.debug(f"STAC Output: {json.dumps(catalog)}")
    logger.debug(f"Items: {json.dumps(items)}")

    return catalog


if __name__ == "__main__":
    payload = {
        'id': 'landsat-8-l1-c1-aws/workflow-publish-landsat/LC08_L1TP_202033_20131129_20170428_01_T1_MTL',
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'id': 'LC08_L1TP_202033_20131129_20170428_01_T1_MTL',
            'collection': 'landsat-8-l1-c1',
            'properties': {},
            'assets': {
                'txt': {
                    'href': 's3://landsat-pds/c1/L8/202/033/LC08_L1TP_202033_20131129_20170428_01_T1/LC08_L1TP_202033_20131129_20170428_01_T1_MTL.txt'
                }
            }
        }],
        'process': {
            "description": "Convert Landsat MTL metadata to STAC and publish",
            "input_collections": ["landsat-8-l1-c1-aws"],
            "workflow": "publish-landsat",
            "output_options": {
                "path_template": "/${collection}/${landsat:wrs_path}/${landsat:wrs_row}/${year}/${month}/${id}",
                "collections": {
                    "landsat-8-l1-c1": ".*"
                }
            },
            "tasks": {
                "publish": {
                    "public": True
                }
            }
        }
    }
    lambda_handler(payload)