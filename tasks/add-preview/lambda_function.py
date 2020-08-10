import boto3
import json
import logging
import numpy
import requests
import shutil
import tempfile

from boto3utils import s3
from os import getenv, path as op
import gdal
from cirruslib import Catalogs
from cirruslib.transfer import download_item_assets, upload_item_assets

import os
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
import rasterio
from rasterio.warp import calculate_default_transform, reproject as _reproject, Resampling
from rasterio.io import MemoryFile
from urllib.parse import urlparse
from traceback import format_exc

# configure logger - CRITICAL, ERROR, WARNING, INFO, DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(getenv('CIRRUS_LOG_LEVEL', 'INFO'))


def lambda_handler(payload, context={}):
    # if this is batch, output to stdout
    if not hasattr(context, "invoked_function_arn"):
        logger.addHandler(logging.StreamHandler())

    logger.debug('Payload: %s' % json.dumps(payload))

    catalog = Catalogs.from_payload(payload)[0]

    # get step configuration
    config = catalog['process']['tasks'].get('add-preview', {})
    outopts = catalog['process'].get('output_options', {})
    assets = config.pop('assets', None)
    thumb = config.pop('thumbnail', False)

    if assets is None:
        msg = f"add-preview: no asset specified for preview, skipping {catalog['id']}"
        logger.error(msg)
        raise Exception(msg)

    # create temporary work directory
    tmpdir = tempfile.mkdtemp()
    items = []
    for item in catalog['features']:
        # find asset to use for preview
        asset = None
        for a in assets:
            if a in item['assets']:
                asset = a
                break
        if asset is None:
            msg = f"add-preview: no asset specified for preview, skipping {item['id']}"
            logger.warning(msg)
            return item

        try:
            # keep original href
            href = item['assets'][asset]['href']
            # download asset
            item = download_item_assets(item, path=tmpdir, assets=[asset])

            # add preview to item
            
            item = add_preview(item, item['assets'][asset]['href'], **config)
            if thumb:
                # add thumbnail to item
                item = add_thumbnail(item, item['assets']['preview']['href'])

            # put back original href
            item['assets'][asset]['href'] = href

            # set item in return catalog to this new item
            #catalog['features'][0] = item._data
            # upload these new assets
            item = upload_item_assets(item, assets=['preview', 'thumbnail'], **outopts)
            items.append(item)
        except Exception as err:
            msg = f"add-preview: failed creating preview/thumbnail for {catalog['id']} ({err})"
            logger.error(msg)
            logger.error(format_exc())
            # remove work directory....very important for Lambdas!
            logger.debug('Removing work directory %s' % tmpdir)
            shutil.rmtree(tmpdir)
            raise Exception(msg) from err

    catalog['features'] = items

    # remove work directory....very important for Lambdas!
    logger.debug('Removing work directory %s' % tmpdir)
    shutil.rmtree(tmpdir)

    return catalog      


def add_thumbnail(item, filename, scale_percent=5):
    """ Add a thumbnail to item, generated from filename """
    fnout = filename.replace('.tif', '.png')
    logging.info(f"Creating thumbnail {fnout} from {filename}")
    try:
        gdal.Translate(fnout, filename, format='PNG', widthPct=scale_percent, heightPct=scale_percent)
        item['assets']['thumbnail'] = {
            'title': 'Thumbnail image',
            'type': 'image/png',
            'roles': ['thumbnail'],
            'href': fnout
        }
        return item
    except Exception as err:
        logger.error(f"Unable to create thumbnail {filename}: {err}")
        raise(err)


def calculate_ccc_values(filename, lo=2.0, hi=96.0, bins=1000):
    """ Determine min and and max values for a Cumulative Count Cut """
    ds = gdal.Open(filename)
    band = ds.GetRasterBand(1)
    # min, max, mean, std
    stats = band.GetStatistics(False, True)
    hist = numpy.array(band.GetHistogram(stats[0], stats[1], buckets=bins, approx_ok=False))
    nchist = (hist/hist.sum()).cumsum() * 100
    lo_inds = numpy.where(nchist <= lo)[0]
    hi_inds = numpy.where(nchist >= hi)[0]
    lo_ind = lo_inds[-1] if len(lo_inds) > 0 else 0
    hi_ind = hi_inds[0] if len(hi_inds) > 0 else len(hist)-1
    ds = None
    q = (stats[1] - stats[0]) / bins
    lo_val = stats[0] + lo_ind * q
    hi_val = stats[0] + hi_ind * q
    return [lo_val, hi_val]


def create_preview(filename, fnout=None, preproj=False, ccc=[2.0, 98.0], exp=None, nodata=0, **kwargs):
    if fnout is None:
        fnout = op.splitext(filename)[0] + '_preview.tif'
    fntmp = fnout.replace('.tif', '_tmp.tif')

    _filename = filename
    if preproj:
        reproject(filename, _filename, crs='epsg:4326')

    try:
        logger.info(f"Creating preview {fnout} from {filename}")
        if exp is not None:
            ds = gdal.Open(_filename)
            band = ds.GetRasterBand(1)
            stats = band.GetStatistics(False, True)
            inmin = stats[0]
            inmax = stats[1]
            logger.debug(f"Stretching {inmin} - {inmax} to 1-255 with exp={exp}")
            gdal.Translate(fntmp, filename, noData=nodata, format='GTiff', outputType=gdal.GDT_Byte,
                       scaleParams=[[inmin, inmax, 1, 255]], exponents=[exp])
        else:
            # ccc stretch
            inmin, inmax = calculate_ccc_values(_filename, lo=ccc[0], hi=ccc[1])
            logger.info(f"Stretching {inmin} - {inmax} to 1-255 with ccc={ccc}")
            gdal.Translate(fntmp, _filename, noData=nodata, format='GTiff', outputType=gdal.GDT_Byte,
                           scaleParams=[[inmin, inmax, 1, 255]])
        cogify(fntmp, fnout)
    except Exception as err:
        logger.error(f"Unable to create preview {filename}: {err}")
        raise(err)
    finally:
        if op.exists(fntmp):
            os.remove(fntmp)
        if preproj and op.exists(_filename):
            os.remove(_filename)
    return fnout


def add_preview(item, filename, **kwargs):
    """ Add a preview and thumbnail image to this STAC Item from <filename> """
    try:
        fnout = create_preview(filename, **kwargs)
        item['assets']['preview'] = {
            'title': 'Preview image',
            'type': 'image/tiff; application=geotiff; cloud-optimized=true',
            'roles': ['overview'],
            'href': fnout
        }
        return item
    except Exception as err:
        logger.error(err)
        raise(err)


def cogify(fin, fout, nodata=None):
    """ Turn a geospatial image into a COG """
    logger.debug(f"Turning {fin} into COG named {fout}")
    output_profile = cog_profiles.get('deflate')
    output_profile.update(dict(BIGTIFF=os.environ.get("BIGTIFF", "IF_SAFER")))
    output_profile['blockxsize'] = 256
    output_profile['blockysize'] = 256

    threads = 1
    overview_blocksize = 128

    config = dict(
        NUM_THREADS=threads,
        GDAL_TIFF_INTERNAL_MASK=os.environ.get("GDAL_TIFF_INTERNAL_MASK", True),
        GDAL_TIFF_OVR_BLOCKSIZE=str(overview_blocksize),
    )
    cog_translate(fin, fout, output_profile, config=config, nodata=nodata, overview_resampling="bilinear",
                  add_mask=False, web_optimized=False)
    return fout


def reproject(fin, fout, crs='EPSG:4326'):
    """ Reproject file using GCPs into a known projection """
    '''
    # TODO - combine cogify with warping if possible
    envs = {
        "driver": "GTiff",
        "interleave": "pixel",
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "DEFLATE",
    }
    '''
    logger.info('Reprojecting to %s: %s into %s' % (crs, fin, fout))
    with rasterio.open(fin) as src:
        if src.crs:
            transform, width, height = calculate_default_transform(
                src.crs, crs, src.width, src.height, *src.bounds)
        else:
            # use GCPs
            transform, width, height = calculate_default_transform(
            src.crs, crs, src.width, src.height, gcps=src.gcps[0])
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': crs,
            'transform': transform,
            'width': width,
            'height': height
        })

        with rasterio.open(fout, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                _reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=crs,
                    resampling=Resampling.nearest)
