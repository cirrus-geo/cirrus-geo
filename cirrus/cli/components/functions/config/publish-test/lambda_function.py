import json
import logging


# logging
logger = logging.getLogger("lambda_function.publish-test")


def lambda_handler(payload, context):
    logger.debug('Payload: %s', json.dumps(payload))

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
        logger.debug("Message: %s", json.dumps(p))
