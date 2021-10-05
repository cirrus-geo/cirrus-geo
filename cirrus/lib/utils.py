import boto3
import json
import logging
import requests
import uuid

from boto3utils import s3
from dateutil.parser import parse as dateparse
from os import getenv
from string import Formatter, Template
from typing import Dict, Optional, List
from collections.abc import Mapping

logger = logging.getLogger(__name__)

batch_client = boto3.client('batch')


def submit_batch_job(payload, arn, queue='basic-ondemand', definition='geolambda-as-batch', name=None):
    # envvars
    STACK_PREFIX = getenv('CIRRUS_STACK')
    CATALOG_BUCKET = getenv('CIRRUS_CATALOG_BUCKET')

    if name is None:
        name = arn.split(':')[-1]

    # upload payload to s3
    url = f"s3://{CATALOG_BUCKET}/batch/{uuid.uuid1()}.json"
    s3().upload_json(payload, url)
    kwargs = {
        'jobName': name,
        'jobQueue': f"{STACK_PREFIX}-{queue}",
        'jobDefinition': f"{STACK_PREFIX}-{definition}",
        'parameters': {
            'lambda_function': arn,
            'url': url
        },
        'containerOverrides': {
            'vcpus': 1,
            'memory': 512,
        }
    }
    logger.debug(f"Submitted batch job with payload {url}")
    response = batch_client.submit_job(**kwargs)
    logger.debug(f"Batch response: {response}")


def get_path(item: Dict, template: str='${collection}/${id}') -> str:
    """Get path name based on STAC Item and template string

    Args:
        item (Dict): A STAC Item.
        template (str, optional): Path template using variables referencing Item fields. Defaults to '${collection}/${id}'.

    Returns:
        [str]: A path name
    """
    _template = template.replace(':', '__colon__')
    subs = {}
    for key in [i[1] for i in Formatter().parse(_template.rstrip('/')) if i[1] is not None]:
        # collection
        if key == 'collection':
            subs[key] = item['collection']
        # ID
        elif key == 'id':
            subs[key] = item['id']
        # derived from date
        elif key in ['year', 'month', 'day']:
            dt = dateparse(item['properties']['datetime'])
            vals = {'year': dt.year, 'month': dt.month, 'day': dt.day}
            subs[key] = vals[key]
        # Item property
        else:
            subs[key] = item['properties'][key.replace('__colon__', ':')]
    return Template(_template).substitute(**subs).replace('__colon__', ':')

def property_match(feature, props):
    prop_checks = []
    for prop in props:
        prop_checks.append(feature['properties'].get(prop, '') == props[prop])
    return all(prop_checks)


# from https://gist.github.com/angstwad/bf22d1822c38a92ec0a9#gistcomment-2622319
def dict_merge(dct, merge_dct, add_keys=True):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    This version will return a copy of the dictionary and leave the original
    arguments untouched.
    The optional argument ``add_keys``, determines whether keys which are
    present in ``merge_dict`` but not ``dct`` should be included in the
    new dict.
    Args:
        dct (dict) onto which the merge is executed
        merge_dct (dict): dct merged into dct
        add_keys (bool): whether to add new keys
    Returns:
        dict: updated dict
    """
    dct = dct.copy()
    if not add_keys:
        merge_dct = {
            k: merge_dct[k]
            for k in set(dct).intersection(set(merge_dct))
        }

    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], Mapping)):
            dct[k] = dict_merge(dct[k], merge_dct[k], add_keys=add_keys)
        else:
            dct[k] = merge_dct[k]

    return dct