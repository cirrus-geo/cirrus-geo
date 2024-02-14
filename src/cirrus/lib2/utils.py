import json
import logging
import re
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from os import getenv
from string import Formatter, Template
from typing import Any, Optional

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
    payload: dict,
    arn: str,
    queue: str = "basic-ondemand",
    definition: str = "geolambda-as-batch",
    name: str = None,
) -> None:
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
        item (dict): A STAC Item.
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


def recursive_compare(
    d1: dict, d2: dict, level: str = "root", print: Callable = print
) -> bool:
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


def extract_record(record: dict):
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


def normalize_event(event: dict):
    if "Records" not in event:
        # not from SQS or SNS
        records = [event]
    else:
        records = event["Records"]
    return records


def extract_event_records(event: dict, convertfn=None):
    for record in normalize_event(event):
        yield extract_record(record)


def payload_from_s3(record: dict) -> dict:
    try:
        payload = s3().read_json(record["url"])
    except KeyError:
        raise NoUrlError(
            "Item does not have a URL and therefore cannot be retrieved from S3"
        )
    return payload


def parse_queue_arn(queue_arn: str) -> dict:
    parsed = QUEUE_ARN_REGEX.match(queue_arn)

    if parsed is None:
        raise ValueError(f"Not a valid SQS ARN: {queue_arn}")

    return parsed.groupdict()


QUEUE_URLS = {}


def get_queue_url(message: dict) -> str:
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


def delete_from_queue(message: dict) -> None:
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


def delete_from_queue_batch(messages: list[dict]) -> dict:
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
    def __init__(
        self,
        fn: Callable,
        params: dict,
        batch_param_name: str,
        batch_size: int = 10,
        dest_name: str = "default",
        logger: logging.Logger = logger,
    ):
        """
        Handles dispatch of messages to AWS functions which support batched operation.
        Provides a context manager (via `get_handler`) to ensure complete dispatch of
        all messages (flushing any fractional batch on exit).

        Args:
          fn (Callable): function to be passed message batches.
          params (dict): dictionary of the named parameters which `fn` takes.
          batch_param_name (str): key to be populated with the messages in `params`
          batch_size (int): size of batches to be sent (defaults to 10)
          dest_name (str): common name of location message is being sent (default is "default")
          logger (logging.Logger): logger class to use (defaults to cirrus.utils.logger)
        """

        self.fn = fn
        self.params = params
        self.batch_param_name = batch_param_name
        self.batch_size = batch_size
        self.dest_name = dest_name
        self._batch = []
        self.logger = logger

    def add(self, message: str):
        """
        Add the given messages to the `_batch`, and ship them if there are more than
        `batch_size`.
        Args:
          message (str): message to be handled by `fn`
        """
        self._batch.append(message)

        if len(self._batch) >= self.batch_size:
            self.execute()

    def _prepare_batch(self) -> list[dict[str, Any]]:
        """Identity function suffices in this base class.  Overriden in subclass, if
        messages need to be massaged before publication.
        """
        return self._batch

    def execute(self):
        if not self._batch:
            return

        params = self.params.copy()
        params[self.batch_param_name] = self._prepare_batch()

        try:
            self.fn(**params)
            self.logger.debug(f"Published {len(params)} payloads to {self.dest_name}")
        finally:
            self._batch = []

    @classmethod
    @contextmanager
    def get_handler(
        cls: "BatchHandler", *args, **kwargs
    ) -> AbstractContextManager["BatchHandler"]:
        publisher = cls(*args, **kwargs)
        try:
            yield publisher
        finally:
            publisher.execute()


@contextmanager
def batch_handler(*args, **kwargs) -> AbstractContextManager[BatchHandler]:
    # TODO: Deprecate this in favor of managed classes
    handler = BatchHandler(*args, **kwargs)
    try:
        yield handler
    finally:
        handler.execute()


class SNSPublisher(BatchHandler):
    """Handles publication of SNS messages via batched interface."""

    def __init__(self, topic_arn: str, **kwargs):
        """extend BatchHandler constructor to add topic_arn and setup SNS Client"""
        self.topic_arn = topic_arn
        self.dest_name = topic_arn.split(":")[-1]
        self._sns_client = boto3.client("sns")
        super().__init__(
            fn=self._sns_client.publish_batch,
            params={"TopicArn": self.topic_arn, "PublishBatchRequestEntries": []},
            batch_param_name="PublishBatchRequestEntries",
            **kwargs,
        )

    def add(self, message: str, message_attrs: Optional[dict] = None):
        """
        Add the given messages to the `_batch`, and ship them if there are more than
        `batch_size`. Override of `BatchHandler.add` to add message attribute support.
        Args:
          messages (str): message to be handled by `fn`
          message_attrs (Optional[dict]): attributes to be added to the message.
        """
        message_params = {"Message": message}
        if message_attrs:
            if len(message_attrs) > 10:
                self.logger.error(
                    "sns to sqs relay only supports 10 attributes: "
                    "https://docs.aws.amazon.com/sns/latest/dg/"
                    "sns-message-attributes.html"
                )
                raise ValueError(f"message_attrs too long: {len(message_attrs)}")
            message_params.update({"MessageAttributes": message_attrs})
        self._batch.append(message_params)

        if len(self._batch) >= self.batch_size:
            self.execute()

    def _prepare_batch(self) -> list[dict[str, Any]]:
        """override of `BatchHandler._prepare_batch` that is consistent with how
        parameters are added to `SNSPublisher._batch`."""
        return [
            dict(Id=str(idx), **message_params)
            for idx, message_params in enumerate(self._batch)
        ]


class SQSPublisher(BatchHandler):
    """Handles publication of SQS messages via batched interface."""

    def __init__(self, queue_url: str, **kwargs):
        """extend BatchHandler constructor to add queue_url and setup SQS Queue"""
        self.queue_url = queue_url
        self.dest_name = queue_url.split("/")[-1]
        self._sqs_client = boto3.resource("sqs")
        self._queue = self._sqs_client.Queue(self.queue_url)
        super().__init__(
            fn=self._queue.send_messages,
            params={},
            batch_param_name="Entries",
            **kwargs,
        )

    def _prepare_batch(self) -> list[dict[str, Any]]:
        """override of `BatchHandler._prepare_batch` that is consistent with how
        parameters are added to `SQSPublisher._batch`."""
        return [
            {
                "Id": str(idx),
                "MessageBody": msg,
            }
            for idx, msg in enumerate(self._batch)
        ]
