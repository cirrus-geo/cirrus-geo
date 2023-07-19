import json
import logging
import re
import uuid
from contextlib import contextmanager
from os import getenv
from string import Formatter, Template

import boto3
from boto3utils import s3
from dateutil.parser import parse as dateparse

from cirrus.lib2.errors import NoUrlError

logger = logging.getLogger(__name__)

QUEUE_ARN_REGEX = re.compile(
    r"^arn:aws:sqs:(?P<region>[\-a-z0-9]+):(?P<account_id>\d+):(?P<name>[\-_a-zA-Z0-9]+)$",
)

batch_client = None
sqs_client = None


def get_batch_client():
    global batch_client
    if batch_client is None:
        batch_client = boto3.client("batch")
    return batch_client


def get_sqs_client():
    global sqs_client
    if sqs_client is None:
        sqs_client = boto3.client("sqs")
    return sqs_client


def submit_batch_job(
    payload, arn, queue="basic-ondemand", definition="geolambda-as-batch", name=None
):
    # envvars
    stack_prefix = getenv("CIRRUS_STACK")
    payload_bucket = getenv("CIRRUS_PAYLOAD_BUCKET")

    if name is None:
        name = arn.split(":")[-1]

    # upload payload to s3
    url = f"s3://{payload_bucket}/batch/{uuid.uuid1()}.json"
    s3().upload_json(payload, url)
    kwargs = {
        "jobName": name,
        "jobQueue": f"{stack_prefix}-{queue}",
        "jobDefinition": f"{stack_prefix}-{definition}",
        "parameters": {"lambda_function": arn, "url": url},
        "containerOverrides": {
            "vcpus": 1,
            "memory": 512,
        },
    }
    logger.debug(f"Submitted batch job with payload {url}")
    response = get_batch_client().submit_job(**kwargs)
    logger.debug(f"Batch response: {response}")


def get_path(item: dict, template: str = "${collection}/${id}") -> str:
    """Get path name based on STAC Item and template string

    Args:
        item (Dict): A STAC Item.
        template (str, optional): Path template using variables referencing Item fields. Defaults to'${collection}/${id}'.

    Returns:
        [str]: A path name
    """
    _template = template.replace(":", "__colon__")
    subs = {}
    for key in [
        i[1] for i in Formatter().parse(_template.rstrip("/")) if i[1] is not None
    ]:
        # collection
        if key == "collection":
            subs[key] = item["collection"]
        # ID
        elif key == "id":
            subs[key] = item["id"]
        # derived from date
        elif key in ["year", "month", "day"]:
            dt = dateparse(item["properties"]["datetime"])
            vals = {"year": dt.year, "month": dt.month, "day": dt.day}
            subs[key] = vals[key]
        # Item property
        else:
            subs[key] = item["properties"][key.replace("__colon__", ":")]
    return Template(_template).substitute(**subs).replace("__colon__", ":")


def recursive_compare(d1, d2, level="root", print=print):
    import difflib

    same = True
    if isinstance(d1, dict) and isinstance(d2, dict):
        if d1.keys() != d2.keys():
            same = False
            s1 = set(d1.keys())
            s2 = set(d2.keys())
            print(f"{level}:")
            for key in s1 - s2:
                print(f"\t- {key}")
            for key in s2 - s1:
                print(f"\t+ {key}")
            print()
            common_keys = s1 & s2
        else:
            common_keys = set(d1.keys())

        for k in common_keys:
            result = recursive_compare(
                d1[k],
                d2[k],
                level=f"{level}.{k}",
            )
            same = same and result

    elif isinstance(d1, list) and isinstance(d2, list):
        if len(d1) != len(d2):
            same = False
        common_len = min(len(d1), len(d2))

        for i in range(common_len):
            result = recursive_compare(
                d1[i],
                d2[i],
                level=f"{level}[{i}]",
            )
            same = same and result

    elif d1 == d2:
        # base case
        pass

    elif (
        isinstance(d1, str)
        and isinstance(d2, str)
        and (len(d1.splitlines()) > 1 or len(d2.splitlines()) > 1)
    ):
        print(f"{level}:")
        diff = difflib.unified_diff(d1.splitlines(), d2.splitlines(), lineterm="")
        for line in diff:
            print(f"\t{line}")
        print()
        same = False

    else:
        print(f"{level}:\n\t- {d1}\n\t+ {d2}\n")
        same = False

    return same


def extract_record(record):
    if "body" in record:
        record = json.loads(record["body"])
    elif "Sns" in record:
        record = record["Sns"]

    if "Message" in record:
        record = json.loads(record["Message"])

    if "url" not in record and "Parameters" in record:
        # this is Batch, get the output payload
        if "url_out" in record["Parameters"]:
            record = {"url": record["Parameters"]["url_out"]}

    return record


def normalize_event(event):
    if "Records" not in event:
        # not from SQS or SNS
        records = [event]
    else:
        records = event["Records"]
    return records


def extract_event_records(event, convertfn=None):
    for record in normalize_event(event):
        yield extract_record(record)


def payload_from_s3(record):
    try:
        payload = s3().read_json(record["url"])
    except KeyError:
        raise NoUrlError(
            "Item does not have a URL and therefore cannot be retrieved from S3"
        )
    return payload


def parse_queue_arn(queue_arn):
    parsed = QUEUE_ARN_REGEX.match(queue_arn)

    if parsed is None:
        raise ValueError(f"Not a valid SQS ARN: {queue_arn}")

    return parsed.groupdict()


QUEUE_URLS = {}


def get_queue_url(message):
    arn = message["eventSourceARN"]

    try:
        return QUEUE_URLS[arn]
    except KeyError:
        pass

    queue_attrs = parse_queue_arn(arn)
    queue_url = get_sqs_client().get_queue_url(
        QueueName=queue_attrs["name"],
        QueueOwnerAWSAccountId=queue_attrs["account_id"],
    )["QueueUrl"]
    QUEUE_URLS[arn] = queue_url
    return queue_url


def delete_from_queue(message):
    receipt_handle = None
    for key in ("receiptHandle", "ReceiptHandle"):
        receipt_handle = message.get(key)
        if receipt_handle is not None:
            break
    else:
        raise ValueError("Message does not have a [rR]eceiptHandle: {message}")

    get_sqs_client().delete_message(
        QueueUrl=get_queue_url(message),
        ReceiptHandle=receipt_handle,
    )


def delete_from_queue_batch(messages):
    queue_url = None
    _messages = []
    bad_messages = []

    for message in messages:
        _queue_url = get_queue_url(message)

        if queue_url is None:
            queue_url = _queue_url
        elif _queue_url != queue_url:
            raise ValueError(
                f"Not all messages from same queue: {queue_url} != {_queue_url}"
            )

        receipt_handle = None
        message_id = None
        for rh_key, mid_key in (
            ("receiptHandle", "messageId"),
            ("ReceiptHandle", "MessageId"),
        ):
            receipt_handle = message.get(rh_key)
            message_id = message.get(mid_key)
            if receipt_handle is not None and message_id is not None:
                _messages.append(
                    {
                        "Id": message_id,
                        "ReceiptHandle": receipt_handle,
                    }
                )
                break
        else:
            bad_messages.append(
                {
                    "Id": "unknown",
                    "SenderFault": True,
                    "Code": "BadMessageFormat",
                    "Message": json.dumps(message),
                }
            )

    resp = get_sqs_client().delete_message_batch(
        QueueUrl=queue_url,
        Entries=_messages,
    )

    try:
        resp["Failed"].extend(bad_messages)
    except KeyError:
        resp["Failed"] = bad_messages

    for success in resp["Successful"]:
        logger.debug("Deleted message from queue %s: %s", queue_url, success)

    for failure in resp["Failed"]:
        logger.error("Failed to delete message from queue %s: %s", queue_url, failure)

    return resp


class BatchHandler:
    def __init__(self, fn, params, batch_param_name, batch_size=10):
        self.fn = fn
        self.params = params
        self.batch_param_name = batch_param_name
        self.batch_size = batch_size
        self._batch = []

    def add(self, element):
        self._batch.append(element)

        if len(self._batch) >= self.batch_size:
            self.execute()

    def execute(self):
        if not self._batch:
            return

        params = self.params.copy()
        params[self.batch_param_name] = self._batch

        try:
            self.fn(**params)
        finally:
            self._batch = []


@contextmanager
def batch_handler(*args, **kwargs):
    handler = BatchHandler(*args, **kwargs)
    try:
        yield handler
    finally:
        handler.execute()
