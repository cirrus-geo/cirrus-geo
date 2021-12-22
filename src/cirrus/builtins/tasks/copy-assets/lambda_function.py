#!/usr/bin/env python

from cirruslib import Catalog, get_task_logger
from cirruslib.transfer import download_item_assets, upload_item_assets
from shutil import rmtree
from tempfile import mkdtemp


def lambda_handler(payload, context={}):
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger("task.copy-assets", catalog=catalog)

    # TODO - make this more general for more items/collections
    item = catalog['features'][0]  # collection=catalog['collections'][0])

    # configuration options
    config = catalog['process']['tasks'].get('copy-assets', {})
    outopts = catalog['process'].get('output_options', {})

    # asset config
    assets = config.get('assets', item['assets'].keys())
    drop_assets = config.get('drop_assets', [])
    # drop specified assets
    for asset in [a for a in drop_assets if a in item['assets'].keys()]:
        logger.debug(f'Dropping asset {asset}')
        item['assets'].pop(asset)
    if type(assets) is str and assets == 'ALL':
        assets = item['assets'].keys()

    # create temporary work directory
    tmpdir = mkdtemp()

    try:
        # copy specified assets
        _assets = [a for a in assets if a in item['assets'].keys()]

        for asset in _assets:
            item = download_item_assets(item, path=tmpdir, assets=[asset])

            item = upload_item_assets(item, assets=[asset], **outopts)

        # replace item in catalog
        catalog['features'][0] = item
    except Exception as err:
        msg = f"copy-assets: failed processing {catalog['id']} ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err
    finally:
        # remove work directory....very important for Lambdas!
        logger.debug('Removing work directory %s' % tmpdir)
        rmtree(tmpdir)

    return catalog
