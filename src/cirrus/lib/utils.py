import json
import logging
import re

from collections.abc import Callable
from datetime import timedelta
from functools import cache
from os import getenv
from typing import Any, Protocol, Self

import boto3

from boto3 import Session
from boto3utils import s3

from cirrus.lib.errors import NoUrlError

logger = logging.getLogger(__name__)

QUEUE_ARN_REGEX = re.compile(
    r"^arn:aws:sqs:(?P<region>[\-a-z0-9]+):(?P<account_id>\d+):(?P<name>[\-_a-zA-Z0-9]+)$",
)

PAYLOAD_ID_REGEX = re.compile(
    r"(?P<collections>.+)/workflow-(?P<workflow>[^/]+)/(?P<itemids>.+)",
)

SINCE_FORMAT_REGEX = re.compile(r"^(\d+)([dhm])$")


def parse_since(since: str) -> timedelta:
    """Convert a since string to a timedelta.

    Args:
        since (str): Contains an integer followed by a unit letter:
            'd' for days, 'h' for hours, 'm' for minutes.

    Returns:
        timedelta object
    """
    match = SINCE_FORMAT_REGEX.match(since)
    if not match:
        raise ValueError(
            f"'{since}' is not a valid 'since' format. "
            f"Expected format: integer followed by 'd' (days), "
            f"'h' (hours), or 'm' (minutes). "
            f"Examples: '7d', '24h', '30m'",
        )

    num, unit = match.groups()

    days = int(num) if unit == "d" else 0
    hours = int(num) if unit == "h" else 0
    minutes = int(num) if unit == "m" else 0
    return timedelta(days=days, hours=hours, minutes=minutes)


def execution_url(execution_arn: str, region: str | None = None) -> str:
    if region is None:
        region = getenv("AWS_REGION", "us-west-2")
    return (
        f"https://{region}.console.aws.amazon.com/states/"
        f"home?region={region}#/v2/executions/details/{execution_arn}"
    )


def cold_start(
    clients=(
        "batch",
        "s3",
        "sns",
        "sqs",
        "stepfunctions",
        "timestream-query",
        "timestream-write",
    ),
    resources=("dynamodb", "sqs"),
):
    """Used in lambda functions to populate the cache of boto clients/resoures.  Default
    values cover core cirrus usages."""
    for client in clients:
        get_client(client)

    for resource in resources:
        get_resource(resource)


@cache
def get_client(
    service: str,
    session: boto3.Session | None = None,
    region: str | None = None,
) -> boto3.client:
    """
    Wrapper around boto3 which implements singleton pattern via @cache
    """
    if session is None:
        session = boto3.Session()
    return session.client(
        service_name=service,
        region_name=region,
    )


@cache
def get_resource(
    service: str,
    session: boto3.Session | None = None,
    region: str | None = None,
):
    """Wrapper around boto3 which implements singleton pattern via @cache"""
    if session is None:
        session = boto3.Session()
    return session.resource(
        service_name=service,
        region_name=region,
    )


def assume_role(
    session: Session,
    iam_role_arn: str | None,
    region: str | None = None,
) -> boto3.Session:
    """
    Acquire and assign new IAM credentials to session if IAM role is available
    """
    if iam_role_arn:
        creds = boto3.client("sts").assume_role(
            RoleArn=iam_role_arn,
            RoleSessionName="CLIrrus_iam_session",
        )["Credentials"]

        session._session.set_config_variable(
            "region",
            region if region else session.region_name,
        )

        session._session.set_credentials(
            access_key=creds["AccessKeyId"],
            secret_key=creds["SecretAccessKey"],
            token=creds["SessionToken"],
        )
        return session

    return session


def recursive_compare(  # noqa: C901
    d1: dict,
    d2: dict,
    level: str = "root",
    print: Callable = print,
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

    if (
        "url" not in record
        and "Parameters" in record
        and "url_out" in record["Parameters"]
    ):
        # this is Batch, get the output payload
        record = {"url": record["Parameters"]["url_out"]}

    return record


def normalize_event(event: dict):
    # if Records in event then from SQS or SNS
    return event.get("Records", [event])


def extract_event_records(event: dict):
    for record in normalize_event(event):
        yield extract_record(record)


def payload_from_s3(record: dict) -> dict:
    try:
        payload = s3().read_json(record["url"])
    except KeyError as e:
        raise NoUrlError(
            "Item does not have a URL and therefore cannot be retrieved from S3",
        ) from e
    return payload


def parse_queue_arn(queue_arn: str) -> dict:
    parsed = QUEUE_ARN_REGEX.match(queue_arn)

    if parsed is None:
        raise ValueError(f"Not a valid SQS ARN: {queue_arn}")

    return parsed.groupdict()


QUEUE_URLS: dict[str, str] = {}


def get_queue_url(message: dict) -> str:
    arn = message["eventSourceARN"]

    try:
        return QUEUE_URLS[arn]
    except KeyError:
        pass

    queue_attrs = parse_queue_arn(arn)
    queue_url = get_client("sqs").get_queue_url(
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

    get_client("sqs").delete_message(
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
                f"Not all messages from same queue: {queue_url} != {_queue_url}",
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
                    },
                )
                break
        else:
            bad_messages.append(
                {
                    "Id": "unknown",
                    "SenderFault": True,
                    "Code": "BadMessageFormat",
                    "Message": json.dumps(message),
                },
            )

    resp = get_client("sqs").delete_message_batch(
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


def build_item_sns_attributes(item: dict) -> dict:  # noqa: C901
    """Create message attributes from Item for publishing to SNS

    Args:
        item (dict): A STAC Item

    Returns:
        dict: Attributes for SNS publishing
    """
    # note that only 10 message attributes can be used with SNS -> SQS when
    # raw message delivery is enabled; we currently have 10 possible attrs
    attrs = {}

    if "collection" in item:
        attrs["collection"] = {
            "DataType": "String",
            "StringValue": item["collection"],
        }

    if "bbox" in item:
        attrs["bbox.ll_lon"] = {
            "DataType": "Number",
            "StringValue": str(item["bbox"][0]),
        }
        attrs["bbox.ll_lat"] = {
            "DataType": "Number",
            "StringValue": str(item["bbox"][1]),
        }
        attrs["bbox.ur_lon"] = {
            "DataType": "Number",
            "StringValue": str(item["bbox"][2]),
        }
        attrs["bbox.ur_lat"] = {
            "DataType": "Number",
            "StringValue": str(item["bbox"][3]),
        }

    if "properties" not in item:
        return attrs

    if "start_datetime" in item["properties"]:
        attrs["start_datetime"] = {
            "DataType": "String",
            "StringValue": item["properties"]["start_datetime"],
        }
    elif "datetime" in item["properties"]:
        attrs["start_datetime"] = {
            "DataType": "String",
            "StringValue": item["properties"]["datetime"],
        }

    if "end_datetime" in item["properties"]:
        attrs["end_datetime"] = {
            "DataType": "String",
            "StringValue": item["properties"]["end_datetime"],
        }
    elif "datetime" in item["properties"]:
        attrs["end_datetime"] = {
            "DataType": "String",
            "StringValue": item["properties"]["datetime"],
        }

    if "datetime" in item["properties"]:
        attrs["datetime"] = {
            "DataType": "String",
            "StringValue": item["properties"]["datetime"],
        }

    if "eo:cloud_cover" in item["properties"]:
        attrs["cloud_cover"] = {
            "DataType": "Number",
            "StringValue": str(item["properties"]["eo:cloud_cover"]),
        }

    if "created" not in item["properties"] or "updated" not in item["properties"]:
        pass
    elif item["properties"]["created"] != item["properties"]["updated"]:
        attrs["status"] = {"DataType": "String", "StringValue": "updated"}
    else:
        attrs["status"] = {"DataType": "String", "StringValue": "created"}

    return attrs


class BatchHandler[T]:
    def __init__(
        self: Self,
        batchable: Callable[[list[T]], Any],
        batch_size: int = 10,
    ) -> None:
        """
        Handles dispatch of messages to AWS functions which support batched
        operation. Provides a context manager to ensure complete dispatch of
        all messages (flushing any fractional batch on exit).

        Args:
          batchable (Callable): function to be passed message batches.
          batch_size (int): size of batches to be sent (defaults to 10)
        """

        self.batchable = batchable
        self.batch_size = batch_size
        self._batch: list[T] = []

    def __enter__(self: Self) -> Self:
        return self

    def __exit__(self: Self, *_, **__) -> None:
        self.execute()

    def add(self: Self, item: T) -> None:
        """
        Add the given messages to the `_batch`, and ship them if there are more than
        `batch_size`.
        Args:
          message (str): message to be handled by `fn`
        """
        self._batch.append(item)

        if len(self._batch) >= self.batch_size:
            self.execute()

    def execute(self: Self) -> Any:
        if not self._batch:
            return None

        try:
            return self.batchable(self._batch)
        finally:
            self._batch = []


class SNSMessage:
    def __init__(
        self: Self,
        body: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._body = body
        self._attrs = attributes if attributes else {}
        self.check_attrs(self._attrs)

    @staticmethod
    def check_attrs(attrs) -> None:
        if len(attrs) > 10:
            raise ValueError(
                f"message_attrs too long: {len(attrs)}. "
                "sns to sqs relay only supports 10 attributes: "
                "https://docs.aws.amazon.com/sns/latest/dg/"
                "sns-message-attributes.html.",
            )

    def render(self: Self) -> dict[str, Any]:
        # we check again just to make sure
        self.check_attrs(self._attrs)
        return {
            "Message": self._body,
            "MessageAttributes": self._attrs,
        }


class DebugLogger(Protocol):  # pragma: no cover
    def debug(self, msg, *args, **kwargs) -> None: ...


class SNSPublisher(BatchHandler[SNSMessage]):
    """Handles publication of SNS messages via batched interface."""

    def __init__(
        self: Self,
        topic_arn: str,
        batch_size: int = 10,
        logger: DebugLogger | None = None,
    ) -> None:
        """extend BatchHandler constructor to add topic_arn and setup SNS Client"""
        super().__init__(batchable=self._send, batch_size=batch_size)
        self.topic_arn = topic_arn
        self.dest_name = topic_arn.split(":")[-1]
        self._sns_client = boto3.client("sns")
        self._logger = logger

    def _send(self: Self, batch: list[SNSMessage]) -> dict[str, Any]:
        """This method is intended to be used with message batches by the
        BatchHandler.execute method.  Use directly with extreme caution"""
        resp = self._sns_client.publish_batch(
            TopicArn=self.topic_arn,
            PublishBatchRequestEntries=self.prepare_batch(batch),
        )
        if self._logger:
            self._logger.debug(
                "Published %s messages to %s",
                len(batch),
                self.dest_name,
            )
        return resp

    def prepare_batch(self: Self, batch: list[SNSMessage]) -> list[dict[str, Any]]:
        return [
            dict(Id=str(idx), **message.render()) for idx, message in enumerate(batch)
        ]


class SQSPublisher(BatchHandler[str]):
    """Handles publication of SQS messages via batched interface."""

    def __init__(
        self: Self,
        queue_url: str,
        batch_size: int = 10,
        logger: DebugLogger | None = None,
    ) -> None:
        """extend BatchHandler constructor to add queue_url and setup SQS Queue"""
        super().__init__(batchable=self._send, batch_size=batch_size)
        self.queue_url = queue_url
        self.dest_name = queue_url.split("/")[-1]
        self._sqs_client = get_resource("sqs")
        self._queue = self._sqs_client.Queue(self.queue_url)
        self._logger = logger

    def _send(self: Self, batch: list[str]) -> dict[str, Any]:
        resp = self._queue.send_messages(Entries=self.prepare_batch(batch))
        if self._logger:
            self._logger.debug(
                "Published %s messages to %s",
                len(batch),
                self.dest_name,
            )
        return resp

    def prepare_batch(self: Self, batch: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "Id": str(idx),
                "MessageBody": msg,
            }
            for idx, msg in enumerate(batch)
        ]
