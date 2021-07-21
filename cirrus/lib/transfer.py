import boto3
import json
import logging
import requests

from boto3utils import s3, secrets
from botocore.exceptions import ClientError
from copy import deepcopy
from dateutil.parser import parse as dateparse
from os import getenv, path as op
from cirrus.lib.utils import get_path

from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# get data bucket to upload to
DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET')

## global dictionary of sessions per bucket
s3_sessions = {}


def get_s3_session(bucket: str=None, s3url: str=None, **kwargs) -> s3:
    """Get boto3-utils s3 class for interacting with an s3 bucket. A secret will be looked for with the name
    `cirrus-creds-<bucket-name>`. If no secret is found the default session will be used

    Args:
        bucket (str, optional): Bucket name to access. Defaults to None.
        url (str, optional): The s3 URL to access. Defaults to None.

    Returns:
        s3: A boto3-utils s3 class
    """
    if s3url:
        parts = s3.urlparse(s3url)
        bucket = parts['bucket']

    if bucket and bucket in s3_sessions:
        return s3_sessions[bucket]
    # otherwise, create new session for this bucket
    creds = deepcopy(kwargs)

    try:
        # get credentials from AWS secret
        secret_name = f"cirrus-creds-{bucket}"
        _creds = secrets.get_secret(secret_name)
        creds.update(_creds)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            # some other client error we cannot handle
            raise e
        logger.info(f"Secret not found, using default credentials: '{secret_name}'")


    requester_pays = creds.pop('requester_pays', False)
    session = boto3.Session(**creds)
    s3_sessions[bucket] = s3(session, requester_pays=requester_pays)
    return s3_sessions[bucket]


def download_from_http(url: str, path: str='') -> str:
    """ Download a file over http and save to path

    Args:
        url (str): A URL to download
        path (str, optional): A local path name to save file. Defaults to '' (current directory)

    Returns:
        str: Local filename of saved file. Basename is the same as the URL basename
    """
    filename = op.join(path, op.basename(url))
    resp = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    return filename


def download_item_assets(item: Dict, path: str='', assets: Optional[List[str]]=None) -> Dict:
    """Download STAC Item assets to local filesystem

    Args:
        item (Dict): A STAC Item dictionary
        path (str, optional): Path to download files to. Defaults to current directory
        assets (Optional[List[str]], optional): List of asset keys to download. Defaults to all assets
        s3_session (s3, optional): boto3-utils s3 object for s3 interactions. Defaults to None

    Returns:
        Dict: A new STAC Item with downloaded assets pointing to newly downloaded files
    """

    # if assets not provided, download all assets
    assets = assets if assets is not None else item['assets'].keys()

    _item = deepcopy(item)

    for a in assets:
        # download each asset
        url = item['assets'][a]['href']
        logger.debug(f"Downloading {url}")

        # http URL to s3 source
        if 'amazonaws.com' in url:
            url = s3.https_to_s3(url)

        filename = None
        # s3 source
        if url.startswith('s3://'):
            parts = s3.urlparse(url)
            s3_session = get_s3_session(parts['bucket'])
            filename = s3_session.download(url, path=path)
        # general http source
        elif url.startswith('http'):
            filename = download_from_http(url, path=path)
        else:
            logger.error(f"Unknown protocol for {url}")

        # if downloaded update href in Item
        if filename:
            _item['assets'][a]['href'] = op.abspath(filename)
    return _item


def upload_item_assets(item: Dict, assets: List[str]=None, public_assets: List[str]=[],
                       path_template: str='${collection}/${id}', s3_urls: bool=False,
                       headers: Dict={}, s3_session: s3=None, **kwargs) -> Dict:
    """Upload Item assets to s3 bucket

    Args:
        item (Dict): STAC Item
        assets (List[str], optional): List of asset keys to upload. Defaults to None.
        public_assets (List[str], optional): List of assets keys that should be public. Defaults to [].
        path_template (str, optional): Path string template. Defaults to '${collection}/${id}'.
        s3_urls (bool, optional): Return s3 URLs instead of http URLs. Defaults to False.
        headers (Dict, optional): Dictionary of headers to set on uploaded assets. Defaults to {}.
        s3_session (s3, optional): boto3-utils s3 object for s3 interactions. Defaults to None

    Returns:
        Dict: A new STAC Item with uploaded assets pointing to newly uploaded file URLs
    """
    # if assets not provided, upload all assets
    _assets = assets if assets is not None else item['assets'].keys()

    # determine which assets should be public
    if type(public_assets) is str and public_assets == 'ALL':
        public_assets = item['assets'].keys()

    # deepcopy of item
    _item = deepcopy(item)

    for key in [a for a in _assets if a in item['assets'].keys()]:
        asset = item['assets'][key]
        filename = asset['href']
        if not op.exists(filename):
            logger.warning(f"Cannot upload {filename}: does not exist")
            continue
        public = True if key in public_assets else False
        _headers = {}
        if 'type' in asset:
            _headers['ContentType'] = asset['type']
        _headers.update(headers)
        # output URL
        url = get_path(item, op.join(path_template, op.basename(filename)))
        # if output URL is relative, put it in the default data bucket
        if url[0:5] != 's3://':
            url = f"s3://{DATA_BUCKET}/{url}"
        parts = s3.urlparse(url)
        s3_session = get_s3_session(parts['bucket'])

        # upload
        logger.debug(f"Uploading {filename} to {url}")
        url_out = s3_session.upload(filename, url, public=public, extra=_headers, http_url=not s3_urls)
        _item['assets'][key]['href'] = url_out
    return _item


