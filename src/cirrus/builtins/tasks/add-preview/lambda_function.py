import numpy
import os
import shutil
import tempfile

import gdal
import rasterio
from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.logging import get_task_logger
from cirrus.lib.transfer import download_item_assets, upload_item_assets
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rasterio.warp import calculate_default_transform, reproject as _reproject, Resampling


def lambda_handler(event, context={}):
    payload = ProcessPayload.from_event(event)
    logger = get_task_logger("task.add-preview", payload=payload)

    # get step configuration
    config = payload.get_task('add-preview', {})
    outopts = payload.process.get('output_options', {})
    assets = config.pop('assets', None)
    thumb = config.pop('thumbnail', False)
    config.pop('batch')

    if assets is None:
        msg = "add-preview: no asset specified for preview"
        logger.error(msg)
        raise Exception(msg)

    # create temporary work directory
    tmpdir = tempfile.mkdtemp()
    items = []
    for item in payload['features']:
        # find asset to use for preview
        asset = None
        for a in assets:
            if a in item['assets']:
                asset = a
                break
        if asset is None:
            msg = "add-preview: no available asset for preview"
            logger.warning(msg)
            items.append(item)
            continue

        try:
            # keep original href
            href = item['assets'][asset]['href']

            # download asset
            item = download_item_assets(item, path=tmpdir, assets=[asset])
            filename = item['assets'][asset]['href']

            # add preview to item
            item['assets']['preview'] = create_preview(filename, logger, **config)
            if thumb:
                # add thumbnail to item
                item['assets']['thumbnail'] = create_thumbnail(item['assets']['preview']['href'], logger)

            # put back original href
            item['assets'][asset]['href'] = href

            # upload these new assets
            item = upload_item_assets(item, assets=['preview', 'thumbnail'], **outopts)
            items.append(item)
        except Exception as err:
            msg = f"add-preview: failed creating preview/thumbnail ({err})"
            logger.error(msg, exc_info=True)
            # remove work directory....very important for Lambdas!
            shutil.rmtree(tmpdir)
            raise Exception(msg) from err

    # remove work directory....very important for Lambdas!
    shutil.rmtree(tmpdir)

    # return new items
    payload['features'] = items
    return payload


def create_thumbnail(filename, logger, scale_percent=5):
    """ Add a thumbnail to item, generated from filename """
    fnout = filename.replace('_preview.tif', '_thumb.png')
    logger.info(f"Creating thumbnail {fnout} from {filename}")
    try:
        gdal.Translate(fnout, filename, format='PNG', widthPct=scale_percent, heightPct=scale_percent)
        return {
            'title': 'Thumbnail image',
            'type': 'image/png',
            'roles': ['thumbnail'],
            'href': fnout
        }
    except Exception as err:
        logger.error(f"Unable to create thumbnail {fnout}: {err}")
        raise(err)


def calculate_ccc_values(filename, logger, lo=2.0, hi=96.0, bins=1000):
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


def create_preview(
    filename,
    logger,
    fnout=None,
    preproj=False,
    ccc=[2.0, 98.0],
    exp=None,
    nodata=0,
    **kwargs,
):
    if fnout is None:
        fnout = os.path.splitext(filename)[0] + '_preview.tif'
    fntmp = fnout.replace('.tif', '_tmp.tif')

    _filename = filename
    if preproj:
        reproject(filename, _filename, logger, crs='epsg:4326')

    try:
        logger.info(f"Creating preview {fnout} from {filename}")
        if exp is not None:
            ds = gdal.Open(_filename)
            band = ds.GetRasterBand(1)
            stats = band.GetStatistics(False, True)
            inmin = stats[0]
            inmax = stats[1]
            logger.debug(f"Stretching {inmin} - {inmax} to 1-255 with exp={exp}")
            gdal.Translate(
                fntmp,
                filename,
                noData=nodata,
                format='GTiff',
                outputType=gdal.GDT_Byte,
                scaleParams=[[inmin, inmax, 1, 255]],
                exponents=[exp],
            )
        else:
            # ccc stretch
            inmin, inmax = calculate_ccc_values(_filename, logger, lo=ccc[0], hi=ccc[1])
            logger.debug(f"Stretching {inmin} - {inmax} to 1-255 with ccc={ccc}")
            gdal.Translate(
                fntmp,
                _filename,
                noData=nodata,
                format='GTiff',
                outputType=gdal.GDT_Byte,
                scaleParams=[[inmin, inmax, 1, 255]],
            )

        cogify(fntmp, fnout, logger)
    except Exception as err:
        logger.error(f"Unable to create preview {filename}: {err}")
        raise(err)
    finally:
        if os.path.exists(fntmp):
            os.remove(fntmp)
        if preproj and os.path.exists(_filename):
            os.remove(_filename)

    return {
        'title': 'Preview image',
        'type': 'image/tiff; application=geotiff; cloud-optimized=true',
        'roles': ['overview'],
        'href': fnout
    }


def cogify(fin, fout, logger, nodata=None):
    """ Turn a geospatial image into a COG """
    logger.info(f"Turning {fin} into COG named {fout}")
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
    cog_translate(
        fin,
        fout,
        output_profile,
        config=config,
        nodata=nodata,
        overview_resampling="bilinear",
        add_mask=False,
        web_optimized=False,
    )
    return fout


def reproject(fin, fout, logger, crs='EPSG:4326'):
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
    logger.debug('Reprojecting to %s: %s into %s' % (crs, fin, fout))
    with rasterio.open(fin) as src:
        if src.crs:
            transform, width, height = calculate_default_transform(
                src.crs,
                crs,
                src.width,
                src.height,
                *src.bounds,
            )
        else:
            # use GCPs
            transform, width, height = calculate_default_transform(
                src.crs,
                crs,
                src.width,
                src.height,
                gcps=src.gcps[0],
            )
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
