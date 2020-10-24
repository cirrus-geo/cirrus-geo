import boto3
import json
import logging
import os.path as op

from boto3utils import s3
from os import getenv
from traceback import format_exc

# environment variables
SNS_TOPIC = getenv('CIRRUS_QUEUE_TOPIC_ARN', None)
SNS_CLIENT = boto3.client('sns') if SNS_TOPIC else None

# logging
logger = logging.getLogger(f"{__name__}.feed-test")


def handler(payload, context):
    logger.debug('Payload: %s' % json.dumps(payload))

    payloads = []
    
    # from SQS or SNS
    if 'Records' in payload:
        for r in payload['Records']:
            if 'body' in r:
                payloads.append(json.loads(r['body']))
            elif 'Sns' in r:
                payloads.append(json.loads(r['Sns']['Message']))
    else:
        payloads = [payload]

    for p in payloads:
        logger.debug(f"Message: {json.dumps(p)}")

    #if SNS_CLIENT:
    #    resp = SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Message=json.dumps(item._data))
    #    logger.debug(f"SNS Publish Response: {resp}")