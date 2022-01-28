import json
from os import getenv

from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.statedb import StateDB
from cirrus.lib.logging import get_task_logger

# envvars
DATA_BUCKET = getenv('CIRRUS_DATA_BUCKET')
API_URL = getenv('CIRRUS_API_URL', None)
# DEPRECATED - additional topics
PUBLISH_TOPICS = getenv('CIRRUS_PUBLISH_SNS', None)

# Cirrus state db
statedb = StateDB()


def lambda_handler(event, context):
    payload = ProcessPayload.from_event(event)
    logger = get_task_logger("task.publish", payload=payload)

    config = payload.get_task('publish', {})
    public = config.get('public', False)
    # additional SNS topics to publish to
    topics = config.get('sns', [])

    # these are the URLs to the canonical records on s3
    s3urls = []

    try:
        logger.debug("Publishing items to s3 and SNS")

        if API_URL is not None:
            link = {
                'title': payload['id'],
                'rel': 'via-cirrus',
                'href': f"{API_URL}/catid/{payload['id']}"
            }
            logger.debug(json.dumps(link))
            # add cirrus-source relation
            for item in payload['features']:
                item['links'].append(link)

        # publish to s3
        s3urls = payload.publish_items_to_s3(DATA_BUCKET, public=public)

        # publish to Cirrus SNS publish topic
        payload.publish_items_to_sns()

        # Deprecated additional topics
        if PUBLISH_TOPICS:
            for topic in PUBLISH_TOPICS.split(','):
                payload.publish_items_to_sns(topic)

        for topic in topics:
            payload.publish_items_to_sns(topic)
    except Exception as err:
        msg = f"publish: failed publishing output items ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err

    try:
        # update job outputs in table
        statedb.set_outputs(payload['id'], outputs=s3urls)
    except Exception as err:
        msg = f"publish: failed setting statedb outputs ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err

    return payload
