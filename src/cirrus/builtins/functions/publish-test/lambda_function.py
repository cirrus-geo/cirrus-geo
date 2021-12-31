import json
import logging


# logging
logger = logging.getLogger("lambda_function.publish-test")


def lambda_handler(event, context):
    logger.debug('Event: %s', json.dumps(event))

    payloads = []

    # from SQS or SNS
    if 'Records' in event:
        for r in event['Records']:
            if 'body' in r:
                payloads.append(json.loads(r['body']))
            elif 'Sns' in r:
                payloads.append(json.loads(r['Sns']['Message']))
    else:
        payloads = [event]

    for p in payloads:
        logger.debug("Message: %s", json.dumps(p))
