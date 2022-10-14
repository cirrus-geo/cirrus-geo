import pytest
import json

from pathlib import Path

from cirrus.lib2 import utils


fixtures = Path(__file__).parent.joinpath('fixtures')
event_dir = fixtures.joinpath('events')


@pytest.fixture
def payloads(boto3utils_s3):
    boto3utils_s3.s3.create_bucket(Bucket="payloads")


@pytest.fixture
def queue(sqs):
    return sqs.create_queue(QueueName='test-queue')['QueueUrl']


same_dicts = [
    ({'a': 1, 'b': 2},
     {'b': 2, 'a': 1}),
    ({'a': 1, 'b': 2},
     {'a': 1, 'b': 2}),
    ({'a': 1, 'b': [1,2,3]},
     {'b': [1,2,3], 'a': 1}),
]


@pytest.mark.parametrize('dicts', same_dicts)
def test_recursive_compare_same(dicts):
    assert utils.recursive_compare(dicts[0], dicts[1])


diff_dicts = [
    ({'a': 1, 'b': 2},
     {'b': 1, 'a': 2}),
    ({'a': 1, 'b': 2},
     {'a': 2, 'b': 1}),
    ({'a': 1, 'b': [1,2,3]},
     {'a': 1, 'b': [1]}),
    ({'a': 1, 'b': 2},
     {'c': 3, 'd': 4}),
]


@pytest.mark.parametrize('dicts', diff_dicts)
def test_recursive_compare_diff(dicts):
    assert not utils.recursive_compare(dicts[0], dicts[1])


@pytest.mark.parametrize('event', event_dir.glob('*.json'))
def test_extract_event_records(event):
    expected = json.loads(event.with_suffix('.json.expected').read_text())
    event = json.loads(event.read_text())
    extracted = list(utils.extract_event_records(event))
    assert(extracted == expected)


def test_payload_from_s3(boto3utils_s3, payloads):
    item = {'id': 'some-id'}
    record = {'url': 's3://payloads/item.json'}
    boto3utils_s3.upload_json(item, record['url'])
    record = utils.payload_from_s3(record)
    assert(record == item)


def test_payload_from_s3_no_url():
    item = {'id': 'some-id'}
    with pytest.raises(utils.NoUrlError):
        utils.payload_from_s3(item)


def test_parse_queue_arn():
    arn = 'arn:aws:sqs:us-west-2:123456789012:cirrus-test-process'
    expected = {
        'region': 'us-west-2',
        'account_id': '123456789012',
        'name': 'cirrus-test-process',
    }
    parsed = utils.parse_queue_arn(arn)
    assert(parsed == expected)


def test_parse_queue_arn_bad():
    with pytest.raises(ValueError):
        utils.parse_queue_arn('not-a-queue-arn')


def test_get_queue_url(sqs, queue):
    arn = 'arn:aws:sqs:us-east-1:123456789012:test-queue'
    msg = {'eventSourceARN': arn}
    url = utils.get_queue_url(msg)
    assert(url == queue)
    # try again to test cached lookups
    url = utils.get_queue_url(msg)
    assert(url == queue)


def test_get_queue_url_bad(sqs):
    arn = 'arn:aws:sqs:us-east-1:123456789012:test-queue-bad'
    msg = {'eventSourceARN': arn}
    with pytest.raises(Exception):
        utils.get_queue_url(msg)


def test_delete_from_queue(sqs, queue):
    arn = 'arn:aws:sqs:us-east-1:123456789012:test-queue'
    sqs.send_message(
        QueueUrl=queue,
        MessageBody='test',
    )
    msg = sqs.receive_message(
        QueueUrl=queue,
        )['Messages'][0]
    msg['eventSourceARN'] = arn
    utils.delete_from_queue(msg)


def test_delete_from_queue_lowercase(sqs, queue):
    arn = 'arn:aws:sqs:us-east-1:123456789012:test-queue'
    sqs.send_message(
        QueueUrl=queue,
        MessageBody='test',
    )
    msg = sqs.receive_message(
        QueueUrl=queue,
        )['Messages'][0]
    msg['receiptHandle'] = msg.pop('ReceiptHandle')
    msg['eventSourceARN'] = arn
    utils.delete_from_queue(msg)


def test_delete_from_queue_bad_message(sqs, queue):
    arn = 'arn:aws:sqs:us-east-1:123456789012:test-queue'
    sqs.send_message(
        QueueUrl=queue,
        MessageBody='test',
    )
    msg = sqs.receive_message(
        QueueUrl=queue,
        )['Messages'][0]
    del msg['ReceiptHandle']
    msg['eventSourceARN'] = arn
    with pytest.raises(ValueError):
        utils.delete_from_queue(msg)
