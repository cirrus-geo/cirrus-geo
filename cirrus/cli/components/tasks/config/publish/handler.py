import json
from os import getenv

from cirruslib import Catalog, StateDB, get_task_logger

# envvars
DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET')
API_URL = getenv('CIRRUS_API_URL', None)
# DEPRECATED - additional topics
PUBLISH_TOPICS = getenv('CIRRUS_PUBLISH_SNS', None)

# Cirrus state db
statedb = StateDB()


def handler(payload, context):
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger(f"{__name__}.publish", catalog=catalog)

    config = catalog['process']['tasks'].get('publish', {})
    public = config.get('public', False)
    # additional SNS topics to publish to
    topics = config.get('sns', [])

    # these are the URLs to the canonical records on s3
    s3urls = []

    try:
        logger.debug("Publishing items to s3 and SNS")

        if API_URL is not None:
            link = {
                'title': catalog['id'],
                'rel': 'via-cirrus',
                'href': f"{API_URL}/catid/{catalog['id']}"
            }
            logger.debug(json.dumps(link))
            # add cirrus-source relation
            for item in catalog['features']:
                item['links'].append(link)

        # publish to s3
        s3urls = catalog.publish_to_s3(DATA_BUCKET, public=public)

        # publish to Cirrus SNS publish topic
        catalog.publish_to_sns()

        # Deprecated additional topics
        if PUBLISH_TOPICS:
            for t in PUBLISH_TOPICS.split(','):
                catalog.publish_to_sns(t)

        for t in topics:
            catalog.publish_to_sns(t)
    except Exception as err:
        msg = f"publish: failed publishing output items ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err

    try:
        # update processing in table
        statedb.set_completed(catalog['id'], outputs=s3urls)
    except Exception as err:
        msg = f"publish: failed setting as complete ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err        

    return catalog