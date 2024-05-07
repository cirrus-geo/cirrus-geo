import json

from pathlib import Path

import pytest

from cirrus.lib import utils
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.sns.models import sns_backends

fixtures = Path(__file__).parent.joinpath("fixtures")
event_dir = fixtures.joinpath("events")


@pytest.fixture()
def queue(sqs):
    return sqs.create_queue(QueueName="test-queue")["QueueUrl"]


@pytest.fixture()
def topic(sns):
    return sns.create_topic(Name="some-topic")["TopicArn"]


same_dicts = [
    ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
    ({"a": 1, "b": 2}, {"a": 1, "b": 2}),
    ({"a": 1, "b": [1, 2, 3]}, {"b": [1, 2, 3], "a": 1}),
]


@pytest.mark.parametrize("dicts", same_dicts)
def test_recursive_compare_same(dicts):
    assert utils.recursive_compare(dicts[0], dicts[1])


diff_dicts = [
    ({"a": 1, "b": 2}, {"b": 1, "a": 2}),
    ({"a": 1, "b": 2}, {"a": 2, "b": 1}),
    ({"a": 1, "b": [1, 2, 3]}, {"a": 1, "b": [1]}),
    ({"a": 1, "b": 2}, {"c": 3, "d": 4}),
]


@pytest.mark.parametrize("dicts", diff_dicts)
def test_recursive_compare_diff(dicts):
    assert not utils.recursive_compare(dicts[0], dicts[1])


@pytest.mark.parametrize("event", event_dir.glob("*.json"))
def test_extract_event_records(event):
    expected = json.loads(event.with_suffix(".json.expected").read_text())
    event = json.loads(event.read_text())
    extracted = list(utils.extract_event_records(event))
    assert extracted == expected


def test_payload_from_s3(boto3utils_s3, payloads):
    item = {"id": "some-id"}
    record = {"url": "s3://payloads/item.json"}
    boto3utils_s3.upload_json(item, record["url"])
    record = utils.payload_from_s3(record)
    assert record == item


def test_payload_from_s3_no_url():
    item = {"id": "some-id"}
    with pytest.raises(utils.NoUrlError):
        utils.payload_from_s3(item)


def test_parse_queue_arn():
    arn = "arn:aws:sqs:us-west-2:123456789012:cirrus-test-process"
    expected = {
        "region": "us-west-2",
        "account_id": "123456789012",
        "name": "cirrus-test-process",
    }
    parsed = utils.parse_queue_arn(arn)
    assert parsed == expected


def test_parse_queue_arn_bad():
    with pytest.raises(ValueError):
        utils.parse_queue_arn("not-a-queue-arn")


def test_get_queue_url(sqs, queue):
    arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
    msg = {"eventSourceARN": arn}
    url = utils.get_queue_url(msg)
    assert url == queue
    # try again to test cached lookups
    url = utils.get_queue_url(msg)
    assert url == queue


def test_get_queue_url_bad(sqs):
    arn = "arn:aws:sqs:us-east-1:123456789012:test-queue-bad"
    msg = {"eventSourceARN": arn}
    with pytest.raises(Exception):
        utils.get_queue_url(msg)


def test_delete_from_queue(sqs, queue):
    arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
    sqs.send_message(
        QueueUrl=queue,
        MessageBody="test",
    )
    msg = sqs.receive_message(
        QueueUrl=queue,
    )["Messages"][0]
    msg["eventSourceARN"] = arn
    utils.delete_from_queue(msg)


def test_delete_from_queue_lowercase(sqs, queue):
    arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
    sqs.send_message(
        QueueUrl=queue,
        MessageBody="test",
    )
    msg = sqs.receive_message(
        QueueUrl=queue,
    )["Messages"][0]
    msg["receiptHandle"] = msg.pop("ReceiptHandle")
    msg["eventSourceARN"] = arn
    utils.delete_from_queue(msg)


def test_delete_from_queue_bad_message(sqs, queue):
    arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
    sqs.send_message(
        QueueUrl=queue,
        MessageBody="test",
    )
    msg = sqs.receive_message(
        QueueUrl=queue,
    )["Messages"][0]
    del msg["ReceiptHandle"]
    msg["eventSourceARN"] = arn
    with pytest.raises(ValueError):
        utils.delete_from_queue(msg)


@pytest.fixture()
def batch_tester():
    class BatchTester:
        def __init__(self):
            self.calls = []
            self.items = []

        def __call__(self, batch):
            self.calls.append(batch)
            self.items.extend(batch)
            return all(isinstance(x, int) for x in batch)

    return BatchTester()


def test_batch_handler(batch_tester):
    handler = utils.BatchHandler(batch_tester)
    handler.add(1)
    handler.execute()
    assert len(batch_tester.calls) == 1
    assert batch_tester.calls[0] == [1]
    assert len(batch_tester.items) == 1
    assert batch_tester.items[0] == 1


def test_batchhandler_context_mgr(batch_tester):
    with utils.BatchHandler(batch_tester) as handler:
        handler.add(1)
        handler.execute()
    assert len(batch_tester.calls) == 1
    assert batch_tester.calls[0] == [1]
    assert len(batch_tester.items) == 1
    assert batch_tester.items[0] == 1


def test_batch_handler_no_items(batch_tester):
    handler = utils.BatchHandler(batch_tester)
    handler.execute()
    assert len(batch_tester.calls) == 0
    assert len(batch_tester.items) == 0


def test_batch_handler_batch(batch_tester):
    items = list(range(10))
    with utils.BatchHandler(batch_tester, batch_size=3) as handler:
        for item in items:
            handler.add(item)

    assert len(batch_tester.calls) == 4
    assert batch_tester.items == items


def test_sqspublisher_batch(sqs, queue):
    items = list(range(10))
    with utils.SQSPublisher(queue_url=queue, batch_size=3) as publisher:
        for item in items:
            publisher.add(str(item))

    msgs = []
    for _ in items:
        msg = int(sqs.receive_message(QueueUrl=queue)["Messages"][0]["Body"])
        msgs.append(msg)
    assert msgs == items


def test_snspublisher_batch(sns, topic):
    items = [str(x) for x in range(10)]
    with utils.SNSPublisher(topic_arn=topic, batch_size=3) as publisher:
        for item in items:
            publisher.add(utils.SNSMessage(body=str(item)))

    sns_backend = sns_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    all_send_notifications = sns_backend.topics[topic].sent_notifications
    assert {e[1] for e in all_send_notifications} == set(items)


def test_snspublisher_mesg_attrs(sns, topic):
    items = [str(x) for x in range(10)]
    with utils.SNSPublisher(topic_arn=topic, batch_size=3) as publisher:
        for item in items:
            publisher.add(
                utils.SNSMessage(
                    str(item),
                    {"status": {"DataType": "String", "StringValue": "succeeded"}},
                ),
            )

    sns_backend = sns_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    all_send_notifications = sns_backend.topics[topic].sent_notifications
    assert {e[1] for e in all_send_notifications} == set(items)


def test_snsmessage_too_many_mesg_attrs() -> None:
    with pytest.raises(ValueError):
        utils.SNSMessage(
            body="too many attrs",
            attributes={
                f"status{i}": {
                    "DataType": "String",
                    "StringValue": "succeeded",
                }
                for i in range(11)
            },
        )
