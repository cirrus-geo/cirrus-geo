import json
from os import getenv

import boto3

from cirrus.lib2.logging import get_task_logger
from cirrus.lib2.process_payload import ProcessPayload
from cirrus.lib2.statedb import StateDB

# envvars
DATA_BUCKET = getenv("CIRRUS_DATA_BUCKET")
API_URL = getenv("CIRRUS_API_URL", None)
PUBLISH_TOPIC_ARN = getenv("CIRRUS_PUBLISH_TOPIC_ARN", None)
# DEPRECATED - additional topics
PUBLISH_TOPICS = getenv("CIRRUS_PUBLISH_SNS", None)

# Cirrus state db
statedb = StateDB()
snsclient = boto3.client("sns")


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
    """Publish this ProcessPayload's items to SNS

    Args:
        topic_arn (str, optional): ARN of SNS Topic. Defaults to PUBLISH_TOPIC_ARN.
    """
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
        s3urls = payload.publish_items_to_s3(DATA_BUCKET, public=public)

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
