import json
import os
from datetime import datetime, timezone

import boto3
from boto3utils import s3, secrets
from botocore.exceptions import ClientError

from cirrus.lib2.logging import get_task_logger
from cirrus.lib2.process_payload import ProcessPayload
from cirrus.lib2.statedb import StateDB
from cirrus.lib2.utils import get_path

# envvars
DATA_BUCKET = os.getenv("CIRRUS_DATA_BUCKET")
API_URL = os.getenv("CIRRUS_API_URL", None)
PUBLISH_TOPIC_ARN = os.getenv("CIRRUS_PUBLISH_TOPIC_ARN", None)
# DEPRECATED - additional topics
PUBLISH_TOPICS = os.getenv("CIRRUS_PUBLISH_SNS", None)

# Cirrus state db
statedb = StateDB()
snsclient = boto3.client("sns")

# global dictionary of sessions per bucket
s3_sessions = {}


def sns_attributes(item) -> dict:
    """Create attributes from Item for publishing to SNS

    Args:
        item (Dict): A STAC Item

    Returns:
        Dict: Attributes for SNS publishing
    """
    # note that sns -> sqs supports only 10 message attributes
    # when not using raw mode, and we currently have 10 attrs
    # possible
    attrs = {}

    if "collection" in item:
        attrs["collection"] = {"DataType": "String", "StringValue": item["collection"]}

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


def publish_items_to_sns(payload, topic_arn, logger):
    responses = []
    for item in payload["features"]:
        responses.append(
            snsclient.publish(
                TopicArn=topic_arn,
                Message=json.dumps(item),
                MessageAttributes=sns_attributes(item),
            )
        )
        logger.debug(f"Published item to {topic_arn}")
    return responses


def get_s3_session(s3url: str, logger) -> s3:
    """Get boto3-utils s3 class for interacting with an s3 bucket. A secret will be looked for with the name
    `cirrus-creds-<bucket-name>`. If no secret is found the default session will be used

    Args:
        s3url (str, optional): The s3 URL to access. Defaults to None.

    Returns:
        s3: A boto3-utils s3 class
    """
    parts = s3.urlparse(s3url)
    bucket = parts["bucket"]

    if bucket and bucket in s3_sessions:
        return s3_sessions[bucket]

    creds = {}
    try:
        # get credentials from AWS secret
        secret_name = f"cirrus-creds-{bucket}"
        creds = secrets.get_secret(secret_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            # some other client error we cannot handle
            raise e
        logger.info(f"Secret not found, using default credentials: '{secret_name}'")

    requester_pays = creds.pop("requester_pays", False)
    session = boto3.Session(**creds)
    s3_sessions[bucket] = s3(session, requester_pays=requester_pays)
    return s3_sessions[bucket]


def publish_items_to_s3(payload, bucket, public, logger) -> list:
    opts = payload.process.get("upload_options", {})
    s3urls = []
    for item in payload["features"]:
        # determine URL of data bucket to publish to- always do this
        url = os.path.join(
            get_path(item, opts.get("path_template")), f"{item['id']}.json"
        )
        if url[0:5] != "s3://":
            url = f"s3://{bucket}/{url.lstrip('/')}"
        if public:
            url = s3.s3_to_https(url)

        # add canonical and self links (and remove existing self link if present)
        item["links"] = [
            link for link in item["links"] if link["rel"] not in ["self", "canonical"]
        ]
        item["links"].insert(
            0, {"rel": "canonical", "href": url, "type": "application/json"}
        )
        item["links"].insert(
            0, {"rel": "self", "href": url, "type": "application/json"}
        )

        # get s3 session
        s3session = get_s3_session(url, logger)

        # if existing item use created date
        now = datetime.now(timezone.utc).isoformat()
        created = None
        if s3session.exists(url):
            old_item = s3session.read_json(url)
            created = old_item["properties"].get("created", None)
        if created is None:
            created = now
        item["properties"]["created"] = created
        item["properties"]["updated"] = now

        # publish to bucket
        headers = opts.get("headers", {})

        extra = {"ContentType": "application/json"}
        extra.update(headers)
        s3session.upload_json(item, url, public=public, extra=extra)
        s3urls.append(url)
        logger.info("Published to s3")

    return s3urls


def lambda_handler(event, context):
    payload = ProcessPayload.from_event(event)
    logger = get_task_logger("task.publish", payload=payload)

    config = payload.get_task("publish", {})
    public = config.get("public", False)
    # additional SNS topics to publish to
    topics = config.get("sns", [])

    # these are the URLs to the canonical records on s3
    s3urls = []

    try:
        logger.debug("Publishing items to s3 and SNS")

        if API_URL is not None:
            link = {
                "title": payload["id"],
                "rel": "via-cirrus",
                "href": f"{API_URL}/catid/{payload['id']}",
            }
            logger.debug(json.dumps(link))
            # add cirrus-source relation
            for item in payload["features"]:
                item["links"].append(link)

        # publish to s3
        s3urls = publish_items_to_s3(payload, DATA_BUCKET, public, logger)

        # publish to Cirrus SNS publish topic
        publish_items_to_sns(payload, PUBLISH_TOPIC_ARN, logger)

        # Deprecated additional topics
        if PUBLISH_TOPICS:
            for topic in PUBLISH_TOPICS.split(","):
                publish_items_to_sns(payload, topic, logger)

        for topic in topics:
            publish_items_to_sns(payload, topic, logger)
    except Exception as err:
        msg = f"publish: failed publishing output items ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err

    try:
        # update job outputs in table
        statedb.set_outputs(payload["id"], outputs=s3urls)
    except Exception as err:
        msg = f"publish: failed setting statedb outputs ({err})"
        logger.error(msg, exc_info=True)
        raise Exception(msg) from err

    return payload.get_payload()
