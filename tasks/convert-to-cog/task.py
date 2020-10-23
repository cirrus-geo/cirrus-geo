import json
import rasterio

from cirruslib import Catalog
from cirruslib.errors import InvalidInput
from cirruslib.transfer import download_item_assets, upload_item_assets, s3_sessions
from os import getenv, remove, path as op
from rasterio.errors import CRSError
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from shutil import rmtree
from tempfile import mkdtemp
from traceback import format_exc


def handler(payload, context={}):
    catalog = Catalog.from_payload(payload)

    # TODO - make this more general for more items/collections
    item = catalog['features'][0] #, collection=catalog['collections'][0])

    # configuration options
    config = catalog['process']['tasks'].get('convert-to-cog', {})
    outopts = catalog['process'].get('output_options', {})
    assets = config.get('assets')

    # create temporary work directory
    tmpdir = mkdtemp()

    try:
        asset_keys = [a for a in assets if a in item['assets'].keys()]
        
        for asset in asset_keys:
            catalog.logger.info(f"Converting {asset} to COG")
            # download asset
            item = download_item_assets(item, path=tmpdir, assets=[asset])

            # cogify
            fn = item['assets'][asset]['href']
            fnout = cogify(fn, op.splitext(fn)[0] + '.tif', **assets[asset])
            item['assets'][asset]['href'] = fnout
            item['assets'][asset]['type'] = "image/tiff; application=geotiff; profile=cloud-optimized"
            with rasterio.open(fnout) as src:
                item['assets'][asset]['proj:shape'] = src.shape
                item['assets'][asset]['proj:transform'] = src.transform

            # upload assets
            item = upload_item_assets(item, assets=[asset], **outopts)
            # cleanup files
            if op.exists(fn):
                remove(fn)
            if op.exists(fnout):
                remove(fnout)

        # add derived_from link
        links = [l['href'] for l in item['links'] if l['rel'] == 'self']
        if len(links) == 1:
            # add derived from link
            item ['links'].append({
                'title': 'Source STAC Item',
                'rel': 'derived_from',
                'href': links[0],
                'type': 'application/json'
            })

        # drop any specified assets
        for asset in [a for a in config.get('drop_assets', []) if a in item['assets'].keys()]:
            item['assets'].pop(asset)

        catalog['features'][0] = item
    except CRSError as err:
        msg = f"convert-to-cog: invalid CRS ({err})"
        catalog.logger.error(msg, exc_info=True)
        raise InvalidInput(msg)
    except s3_sessions[list(s3_sessions)[0]].s3.exceptions.NoSuchKey as err:
        msg = f"convert-to-cog: failed fetching {asset} asset ({err})"
        catalog.logger.error(msg, exc_info=True)
        raise InvalidInput(msg)
    except Exception as err:
        msg = f"convert-to-cog: failed creating COGs ({err})"
        catalog.logger.error(msg, exc_info=True)
        raise Exception(msg)
    finally:
        # remove work directory....very important for Lambdas!
        catalog.logger.debug('Removing work directory %s' % tmpdir)
        rmtree(tmpdir)

    return catalog


def cogify(fin, fout, nodata=None, web_optimized=False, blocksize=256,
           overview_blocksize=128, overview_resampling='nearest'):
    """ Turn a geospatial image into a COG """
    output_profile = cog_profiles.get('deflate')
    output_profile.update({
        "BIGTIFF": getenv("BIGTIFF", "IF_SAFER"),
        "blockxsize": blocksize,
        "blockysize": blocksize,
        "PREDICTOR": 2
    })

    config = {
        "NUM_THREADS": "ALL_CPUS",
        "GDAL_TIFF_INTERNAL_MASK": getenv("GDAL_TIFF_INTERNAL_MASK", True),
        "GDAL_TIFF_OVR_BLOCKSIZE": str(overview_blocksize)
    }
    cog_translate(fin, fout, output_profile, config=config,
                  nodata=nodata, overview_resampling=overview_resampling,
                  add_mask=False, web_optimized=web_optimized)
    return fout