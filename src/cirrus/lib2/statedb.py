import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key

from .eventdb import EventDB, StateEnum

STATES = ["PROCESSING", "COMPLETED", "FAILED", "INVALID", "ABORTED"]

# logging
logger = logging.getLogger(__name__)


def get_payload_bucket():
    return os.getenv("CIRRUS_PAYLOAD_BUCKET")


def get_state_db():
    return os.getenv("CIRRUS_STATE_DB")


class StateDB:
    limit = None

    def __init__(
        self,
        table_name: Optional[str] = None,
        eventdb: Optional[EventDB] = None,
        session: Optional[boto3.Session] = None,
    ):
        """Initialize a StateDB instance using the Cirrus State DB table

        Args:
            table_name (str, optional): The Cirrus StateDB Table name. Defaults to os.getenv('CIRRUS_STATE_DB', None).
        """
        table_name = table_name if table_name else get_state_db()

        if not table_name:
            raise ValueError("env var CIRRUS_STATE_DB must be defined")

        if not session:
            session = boto3.Session()

        # initialize client
        self.db = session.resource("dynamodb")
        self.table_name = table_name
        self.table = self.db.Table(table_name)

        if eventdb:
            self.eventdb = eventdb
        else:
            self.eventdb = EventDB(session=session)

    def delete_item(self, payload_id: str):
        key = self.payload_id_to_key(payload_id)
        response = self.table.delete_item(Key=key)
        logger.debug("Removed item", extra=key)
        return response

    def delete(self):
        # delete table (used for testing)
        self.table.delete()
        self.table.wait_until_not_exists()

    def get_dbitem(self, payload_id: str) -> Dict:
        """Get a DynamoDB item

        Args:
            payload_id (str): Payload ID

        Raises:
            Exception: Error getting item

        Returns:
            Dict: DynamoDB Item
        """
        key = self.payload_id_to_key(payload_id)
        try:
            response = self.table.get_item(Key=key)
            return response.get("Item", None)
        except Exception as err:
            msg = "Error fetching item"
            logger.error(msg, extra=key.update({"error": err}), exc_info=True)
            raise Exception(msg)

    def get_dbitems(self, payload_ids: List[str]) -> List[Dict]:
        """Get multiple DynamoDB Items

        Args:
            payload_ids (List[str]): A List of Payload IDs

        Raises:
            Exception: Error getting items

        Returns:
            List[Dict]: A list of DynamoDB Items
        """
        try:
            resp = self.db.meta.client.batch_get_item(
                RequestItems={
                    self.table_name: {
                        "Keys": [self.payload_id_to_key(x) for x in set(payload_ids)]
                    }
                }
            )
            items = []
            for r in resp["Responses"][self.table_name]:
                items.append(r)
            logger.debug(f"Fetched {len(items)} items")
            return items
        except Exception:
            msg = "Error fetching items"
            logger.error(msg, exc_info=True)
            raise Exception(msg)

    def get_counts(
        self, collections_workflow: str, limit: int = None, **query_kwargs
    ) -> Dict:
        """Get counts by query

        Args:
            collections_workflow (str): /-separated list of collections
                (input or output depending on index).
            limit (int, optional): The max number to return, anything over will be
                reported as "<limit>+", e.g. "1000+".

            Additional kwargs used by StateDB.query() are also supported here.

        Returns:
            Dict: JSON containing counts key with counts for each state requested.
        """
        query_kwargs["collections_workflow"] = collections_workflow
        query_kwargs["select"] = "COUNT"

        resp = self.query(**query_kwargs)
        counts = resp.get("Count", 0)

        while "LastEvaluatedKey" in resp and (not limit or counts <= limit):
            query_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            resp = self.query(**query_kwargs)
            counts += resp["Count"]

        if limit and counts > limit:
            counts = f"{limit}+"

        return counts

    def get_items_page(
        self,
        collections_workflow: str,
        limit=100,
        nextkey: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Get Items by query

        Args:
            collections_workflow (str): /-separated list of input collections_workflow
            limit (int, optional): number of items to return per page
            nextkey (str, optional): the item ID from which to begin returned page

            Additional kwargs used by StateDB.query() are also supported here.

        Returns:
            Dict: List of Items
        """
        items: Dict[str, Any] = {"items": []}
        kwargs.update(
            {
                "collections_workflow": collections_workflow,
                "Limit": limit,
            }
        )

        if nextkey:
            dbitem = self.get_dbitem(nextkey)
            startkey = {
                key: dbitem[key]
                for key in [
                    "collections_workflow",
                    "itemids",
                    "state_updated",
                    "updated",
                ]
            }
            kwargs["ExclusiveStartKey"] = startkey

        resp = self.query(**kwargs)

        for i in resp["Items"]:
            items["items"].append(self.dbitem_to_item(i))

        if "LastEvaluatedKey" in resp:
            items["nextkey"] = self.key_to_payload_id(resp["LastEvaluatedKey"])

        return items

    def get_items(self, *args, limit=None, **kwargs) -> Dict:
        """Get items from database

        Args:
            limit (int, optional): Maximum number of items to return. Defaults to None.

        Returns:
            Dict: StateDB Items
        """
        resp = self.get_items_page(*args, **kwargs)
        items = resp["items"]
        while "nextkey" in resp and (limit is None or len(items) < limit):
            resp = self.get_items_page(*args, nextkey=resp["nextkey"], **kwargs)
            items += resp["items"]
        if limit is None or len(items) < limit:
            return items
        return items[:limit]

    def get_state(self, payload_id: str) -> str:
        """Get current state of Item
        Args:
            payload_id (str): The Payload ID
        Returns:
            str: Current state: PROCESSING, COMPLETED, FAILED, INVALID, ABORTED
        """
        response = self.table.get_item(Key=self.payload_id_to_key(payload_id))
        if "Item" in response:
            return response["Item"]["state_updated"].split("_")[0]
        else:
            # assuming no such item in database
            return ""

    def get_states(self, payload_ids: List[str]) -> Dict[str, str]:
        """Get current state of items
        Args:
            payload_ids (List[str]): List of Payload IDs
        Returns:
            Dict[str, str]: Dictionary of Payload IDs to state
        """
        states = {}
        for dbitem in self.get_dbitems(payload_ids):
            item = self.dbitem_to_item(dbitem)
            states[item["payload_id"]] = item["state"]
        return states

    def claim_processing(self, payload_id):
        """Sets payload_id to PROCESSING to claim it (preventing other runs)"""
        now = datetime.now(timezone.utc).isoformat()
        key = self.payload_id_to_key(payload_id)

        expr = (
            "SET "
            "created = if_not_exists(created, :created), "
            "state_updated=:state_updated, updated=:updated"
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ConditionExpression="NOT begins_with(state_updated, :proc)",
            ExpressionAttributeValues={
                ":created": now,
                ":state_updated": f"PROCESSING_{now}",
                ":updated": now,
                ":proc": "PROCESSING",
            },
        )
        logger.debug("Claimed processing", extra=key)
        return response

    def set_processing(self, payload_id: str, execution_arn: str) -> Dict[str, Any]:
        """Adds execution to existing item or creates new"""
        now = datetime.now(timezone.utc).isoformat()
        key = self.payload_id_to_key(payload_id)

        expr = (
            "SET "
            "created = if_not_exists(created, :created), "
            "state_updated=:state_updated, updated=:updated, "
            "executions = list_append(if_not_exists(executions, :empty_list), :exes)"
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ":created": now,
                ":state_updated": f"PROCESSING_{now}",
                ":updated": now,
                ":empty_list": [],
                ":exes": [execution_arn],
            },
        )
        logger.debug("Add execution", extra=key.update({"execution": execution_arn}))

        self.write_timeseries_record(key, StateEnum.PROCESSING, now, execution_arn)

        return response

    def set_outputs(self, payload_id: str, outputs: List[str]) -> str:
        """Set this item's outputs

        Args:
            payload_id (str): The Cirrus Payload
            outputs ([str]): List of URLs to output Items

        Returns:
            str: DynamoDB response
        """
        now = datetime.now(timezone.utc).isoformat()
        key = self.payload_id_to_key(payload_id)

        expr = (
            "SET "
            "created = if_not_exists(created, :created), "
            "updated=:updated, "
            "outputs=:outputs"
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ":created": now,
                ":updated": now,
                ":outputs": outputs,
            },
        )
        logger.debug("set outputs", extra=key.update({"outputs": outputs}))
        return response

    def set_completed(
        self,
        payload_id: str,
        outputs: Optional[List[str]] = None,
        execution_arn: Optional[str] = None,
    ) -> str:
        """Set this item as COMPLETED

        Args:
            payload_id (str): The Cirrus Payload
            outputs (Optional[[str]], optional): List of URLs to output Items. Defaults to None.
            execution_arn (Optional[str]): The Step Function execution ARN.

        Returns:
            str: DynamoDB response
        """
        now = datetime.now(timezone.utc).isoformat()
        key = self.payload_id_to_key(payload_id)

        expr = (
            "SET "
            "created = if_not_exists(created, :created), "
            "state_updated=:state_updated, updated=:updated"
        )
        expr_attrs = {
            ":created": now,
            ":state_updated": f"COMPLETED_{now}",
            ":updated": now,
        }

        if outputs is not None:
            expr += ", outputs=:outputs"
            expr_attrs[":outputs"] = outputs

        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues=expr_attrs,
        )
        logger.debug("set completed", extra=key.update({"outputs": outputs}))

        if execution_arn:
            self.write_timeseries_record(key, StateEnum.COMPLETED, now, execution_arn)
        else:
            logger.debug("set completed called with no execution ARN")

        return response

    def set_failed(self, payload_id, msg, execution_arn: Optional[str] = None):
        """Adds new item as failed"""
        """ Adds new item with state function execution """
        now = datetime.now(timezone.utc).isoformat()
        key = self.payload_id_to_key(payload_id)

        expr = (
            "SET "
            "created = if_not_exists(created, :created), "
            "state_updated=:state_updated, updated=:updated, "
            "last_error=:last_error"
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ":created": now,
                ":state_updated": f"FAILED_{now}",
                ":updated": now,
                ":last_error": msg,
            },
        )
        logger.debug("set failed", extra=key.update({"last_error": msg}))

        if execution_arn:
            self.write_timeseries_record(key, StateEnum.FAILED, now, execution_arn)

        return response

    def set_invalid(
        self, payload_id: str, msg: str, execution_arn: Optional[str] = None
    ) -> str:
        """Set this item as INVALID

        Args:
            payload_id (str): The Cirrus Payload
            msg (str): An error message to include in DynamoDB Item
            execution_arn (Optional[str]): The Step Function execution ARN.

        Returns:
            str: DynamoDB response
        """
        now = datetime.now(timezone.utc).isoformat()
        key = self.payload_id_to_key(payload_id)

        expr = (
            "SET "
            "created = if_not_exists(created, :created), "
            "state_updated=:state_updated, updated=:updated, "
            "last_error=:last_error"
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ":created": now,
                ":state_updated": f"INVALID_{now}",
                ":updated": now,
                ":last_error": msg,
            },
        )
        logger.debug("set invalid", extra=key.update({"last_error": msg}))

        if execution_arn:
            self.write_timeseries_record(key, StateEnum.INVALID, now, execution_arn)

        return response

    def set_aborted(self, payload_id: str, execution_arn: Optional[str] = None) -> str:
        """Set this item as ABORTED

        Args:
            payload_id (str): The Cirrus Payload
            execution_arn (Optional[str]): The Step Function execution ARN.

        Returns:
            str: DynamoDB response
        """
        now = datetime.now(timezone.utc).isoformat()
        key = self.payload_id_to_key(payload_id)

        expr = (
            "SET "
            "created = if_not_exists(created, :created), "
            "state_updated=:state_updated, updated=:updated"
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ":created": now,
                ":state_updated": f"ABORTED_{now}",
                ":updated": now,
            },
        )

        logger.debug("set aborted")

        if execution_arn:
            self.write_timeseries_record(key, StateEnum.ABORTED, now, execution_arn)

        return response

    def query(
        self,
        collections_workflow: str,
        state: str = None,
        since: str = None,
        select: str = "ALL_ATTRIBUTES",
        sort_ascending: bool = False,
        sort_index: str = "updated",
        error_begins_with: str = None,
        **kwargs,
    ) -> Dict:
        """Perform a single Query on a DynamoDB index

        Args:
            collections_workflow (str): The complete has to query
            state (Optional[str], optional): State of Items to get. Defaults to None.
                Valid values: PROCESSING, COMPLETED, FAILED, INVALID, ABORTED.
            since (Optional[str], optional): Get Items since this amount of time
                in the past. Defaults to None.
            select (str, optional): DynamoDB Select statement (ALL_ATTRIBUTES, COUNT).
                Defaults to 'ALL_ATTRIBUTES'.
            sort_ascending (bool, optional): Determines which direction the index of
                the results will be sorted. Defaults to False/Descending.
            sort_index (str, optional): Determines which index to use for sorting,
                if not applying a filter (default, state_updated, updated).
                If default, sorting will use primary index and sort by item_ids
            error_begins_with (Optional[str], optional): Filter by error prefix.

            Additional kwargs used by dynamodb.query() are also supported here.

        Returns:
            Dict: DynamoDB response
        """
        index = None if sort_index == "default" else sort_index

        if error_begins_with:
            kwargs["FilterExpression"] = Attr("last_error").begins_with(
                error_begins_with
            )

        # always use the hash of the table which is same in all Global Secondary Indices
        expr = Key("collections_workflow").eq(collections_workflow)
        if since:
            start = datetime.now(timezone.utc) - self.since_to_timedelta(since)
            begin = f"{start.isoformat()}"
            end = f"{datetime.now(timezone.utc).isoformat()}"

            if state:
                index = "state_updated"
                expr = expr & Key(index).between(f"{state}_{begin}", f"{state}_{end}")
            else:
                index = "updated"
                expr = expr & Key(index).between(begin, end)

        elif state:
            index = "state_updated"
            expr = expr & Key(index).begins_with(state)

        exclusive_start_key_filters = ["collections_workflow", "itemids"]

        if index:
            kwargs["IndexName"] = index
            exclusive_start_key_filters.append(index)

        if "ExclusiveStartKey" in kwargs:
            kwargs["ExclusiveStartKey"] = {
                k: kwargs["ExclusiveStartKey"][k] for k in exclusive_start_key_filters
            }

        kwargs.update(
            {
                "KeyConditionExpression": expr,
                "Select": select,
                "ScanIndexForward": sort_ascending,
            }
        )

        if self.limit and ("Limit" not in kwargs or self.limit < kwargs["Limit"]):
            kwargs["Limit"] = self.limit

        logger.debug(kwargs)
        resp = self.table.query(**kwargs)

        return resp

    @classmethod
    def dbitem_to_item(
        cls, dbitem: Dict, region: str = os.getenv("AWS_REGION", "us-west-2")
    ) -> Dict:
        state, updated = dbitem["state_updated"].split("_")
        collections, workflow = dbitem["collections_workflow"].rsplit("_", maxsplit=1)
        item = {
            "payload_id": cls.key_to_payload_id(dbitem),
            "collections": collections,
            "workflow": workflow,
            "items": dbitem["itemids"],
            "state": state,
            "created": dbitem["created"],
            "updated": dbitem["updated"],
            "payload": cls.payload_id_to_url(cls.key_to_payload_id(dbitem)),
        }
        if "executions" in dbitem:
            base_url = f"https://{region}.console.aws.amazon.com/states/home?region={region}#/v2/executions/details/"
            item["executions"] = [base_url + f"{e}" for e in dbitem["executions"]]
        if "outputs" in dbitem:
            item["outputs"] = dbitem["outputs"]
        if "last_error" in dbitem:
            item["last_error"] = dbitem["last_error"]
        return item

    @staticmethod
    def payload_id_to_key(payload_id: str) -> Dict:
        """Create DynamoDB Key from Payload ID

        Args:
            payload_id (str): The Payload ID

        Returns:
            Dict: Dictionary containing the DynamoDB Key
        """
        parts1 = payload_id.split("/workflow-")
        parts2 = parts1[1].split("/", maxsplit=1)
        key = {
            "collections_workflow": parts1[0] + f"_{parts2[0]}",
            "itemids": "" if len(parts2) == 1 else parts2[1],
        }
        return key

    @staticmethod
    def key_to_payload_id(key: Dict) -> str:
        """Get Payload ID given a DynamoDB Key

        Args:
            key (Dict): DynamoDB Key

        Returns:
            str: Payload ID
        """
        parts = key["collections_workflow"].rsplit("_", maxsplit=1)
        return f"{parts[0]}/workflow-{parts[1]}/{key['itemids']}"

    @staticmethod
    def payload_id_to_bucket_key(payload_id, payload_bucket=None):
        if not payload_bucket:
            payload_bucket = get_payload_bucket()
        return (payload_bucket, f"{payload_id}/input.json")

    @classmethod
    def payload_id_to_url(cls, payload_id, payload_bucket=None):
        bucket, key = cls.payload_id_to_bucket_key(
            payload_id,
            payload_bucket=payload_bucket,
        )
        return f"s3://{bucket}/{key}"

    @classmethod
    def payload_key_to_url(cls, key, payload_bucket=None):
        return cls.payload_id_to_url(
            cls.key_to_payload_id(key),
            payload_bucket=payload_bucket,
        )

    @staticmethod
    def since_to_timedelta(since: str) -> timedelta:
        """Convert a `since` field to a timedelta.

        Args:
            since (str): Contains an integer followed by a unit letter: 'd' for days, 'h' for hours, 'm' for minutes

        Returns:
            timedelta: [description]
        """
        unit = since[-1]
        # days, hours, or minutes
        assert unit in ["d", "h", "m"]
        days = int(since[0:-1]) if unit == "d" else 0
        hours = int(since[0:-1]) if unit == "h" else 0
        minutes = int(since[0:-1]) if unit == "m" else 0
        return timedelta(days=days, hours=hours, minutes=minutes)

    def write_timeseries_record(
        self,
        key: Dict[str, str],
        state: StateEnum,
        event_time: str,
        execution_arn: str,
    ) -> None:
        if self.eventdb:
            self.eventdb.write_timeseries_record(key, state, event_time, execution_arn)
