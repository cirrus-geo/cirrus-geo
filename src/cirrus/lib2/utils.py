import boto3
import json
import logging
import uuid
import re

from boto3utils import s3
from os import getenv

from cirrus.lib2.errors import NoUrlError


logger = logging.getLogger(__name__)

QUEUE_ARN_REGEX = re.compile(
    r'^arn:aws:sqs:(?P<region>[\-a-z0-9]+):(?P<account_id>\d+):(?P<name>[\-_a-zA-Z0-9]+)$',
)

batch_client = None
sqs_client = None


def get_batch_client():
    global batch_client
    if batch_client is None:
        batch_client = boto3.client('batch')
    return batch_client


def get_sqs_client():
    global sqs_client
    if sqs_client is None:
        sqs_client = boto3.client('sqs')
    return sqs_client


def submit_batch_job(payload, arn, queue='basic-ondemand', definition='geolambda-as-batch', name=None):
    # envvars
    STACK_PREFIX = getenv('CIRRUS_STACK')
    PAYLOAD_BUCKET = getenv('CIRRUS_PAYLOAD_BUCKET')

    if name is None:
        name = arn.split(':')[-1]

    # upload payload to s3
    url = f"s3://{PAYLOAD_BUCKET}/batch/{uuid.uuid1()}.json"
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
    response = get_batch_client().submit_job(**kwargs)
    logger.debug(f"Batch response: {response}")


def recursive_compare(d1, d2, level='root', print=print):
    same = True
    if isinstance(d1, dict) and isinstance(d2, dict):
        if d1.keys() != d2.keys():
            same = False
            s1 = set(d1.keys())
            s2 = set(d2.keys())
            print(f'{level:<20} + {s1-s2} - {s2-s1}')
            common_keys = s1 & s2
        else:
            common_keys = set(d1.keys())

        for k in common_keys:
            same = same and recursive_compare(
                d1[k],
                d2[k],
                level=f'{level}.{k}',
            )

    elif isinstance(d1, list) and isinstance(d2, list):
        if len(d1) != len(d2):
            same = False
            print(f'{level:<20} len1={len(d1)}; len2={len(d2)}')
        common_len = min(len(d1), len(d2))

        for i in range(common_len):
            same = same and recursive_compare(
                d1[i],
                d2[i],
                level=f'{level}[{i}]',
            )

    elif d1 != d2:
        print(f'{level:<20} {d1} != {d2}')
        same = False

    else:
        # base case d1 == d2
        pass

    return same


def extract_record(record):
    if 'body' in record:
        record = json.loads(record['body'])
    elif 'Sns' in record:
        record = record['Sns']

    if 'Message' in record:
        record = json.loads(record['Message'])

    if 'url' not in record and 'Parameters' in record and 'url' in record['Parameters']:
        # this is Batch, get the output payload
        record = {'url': record['Parameters']['url'].replace('.json', '_out.json')}

    return record


def normalize_event(event):
    if 'Records' not in event:
        # not from SQS or SNS
        records = [event]
    else:
        records = event['Records']
    return records


def extract_event_records(event, convertfn=None):
    for record in normalize_event(event):
        yield extract_record(record)


def payload_from_s3(record):
    try:
        payload = s3().read_json(record['url'])
    except KeyError:
        raise NoUrlError('Item does not have a URL and therefore cannot be retrieved from S3')
    return payload


def parse_queue_arn(queue_arn):
    parsed = QUEUE_ARN_REGEX.match(queue_arn)

    if parsed is None:
        raise ValueError(f'Not a valid SQS ARN: {queue_arn}')

    return parsed.groupdict()


QUEUE_URLS = {}

def get_queue_url(message):
    arn = message['eventSourceARN']

    try:
        return QUEUE_URLS[arn]
    except KeyError:
        pass

    queue_attrs = parse_queue_arn(arn)
    queue_url = get_sqs_client().get_queue_url(
        QueueName=queue_attrs['name'],
        QueueOwnerAWSAccountId=queue_attrs['account_id'],
    )['QueueUrl']
    QUEUE_URLS[arn] = queue_url
    return queue_url


def delete_from_queue(message):
    receipt_handle = None
    for key in ('receiptHandle', 'ReceiptHandle'):
        receipt_handle = message.get(key)
        if receipt_handle is not None:
            break
    else:
        raise ValueError('Message does not have a [rR]eceiptHandle: {message}')

    get_sqs_client().delete_message(
        QueueUrl=get_queue_url(message),
        ReceiptHandle=receipt_handle,
    )
