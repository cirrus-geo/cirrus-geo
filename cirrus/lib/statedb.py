import boto3
import json
import logging
import os

from boto3utils import s3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List

# envvars
CATALOG_BUCKET = os.getenv('CIRRUS_CATALOG_BUCKET')

STATES = ['PROCESSING', 'COMPLETED', 'FAILED', 'INVALID']

# logging
logger = logging.getLogger(__name__)


class StateDB:

    def __init__(self, table_name: str=os.getenv('CIRRUS_STATE_DB', 'test')):
        """Initialize a StateDB instance using the Cirrus State DB table

        Args:
            table_name (str, optional): The Cirrus StateDB Table name. Defaults to os.getenv('CIRRUS_STATE_DB', None).
        """
        # initialize client
        self.db = boto3.resource('dynamodb')
        self.table_name = table_name
        self.table = self.db.Table(table_name)

    def delete_item(self, catid: str):
        key = self.catid_to_key(catid)
        response = self.table.delete_item(Key=key)
        logger.debug("Removed item", extra=key)
        return response

    def delete(self):
        # delete table (used for testing)
        self.table.delete()
        self.table.wait_until_not_exists()        

    def get_dbitem(self, catid: str) -> Dict:
        """Get a DynamoDB item

        Args:
            catid (str): Catalog ID

        Raises:
            Exception: Error getting item

        Returns:
            Dict: DynamoDB Item
        """
        key=self.catid_to_key(catid)
        try:
            response = self.table.get_item(Key=key)
            return response.get('Item', None)
        except Exception as err:
            msg = "Error fetching item"
            logger.error(msg, extra=key.update({'error': err}), exc_info=True)
            raise Exception(msg)

    def get_dbitems(self, catids: List[str]) -> List[Dict]:
        """Get multiple DynamoDB Items

        Args:
            catids (List[str]): A List of Catalog IDs

        Raises:
            Exception: Error getting items

        Returns:
            List[Dict]: A list of DynamoDB Items
        """
        try:
            resp = self.db.meta.client.batch_get_item(RequestItems={
                self.table_name: {
                    'Keys': [self.catid_to_key(id) for id in catids]
                }
            })
            items = []
            for r in resp['Responses'][self.table_name]:
                items.append(r)
            logger.debug(f"Fetched {len(items)} items")
            return items
        except Exception as err:
            msg = f"Error fetching items"
            logger.error(msg, exc_info=True)
            raise Exception(msg)

    def get_counts(self, collections_workflow: str, state: str=None, since: str=None, limit: int=None) -> Dict:
        """Get counts by query

        Args:
            collections_workflow (str): /-separated list of collections (input or output depending on index)
            state (Optional[str], optional): State of Items to get. Defaults to None.
            since (Optional[str], optional): Get Items since this amount of time in the past. Defaults to None.
            limit (int, optional): The max number to return, anything over will be reported as "<limit>+", e.g. "1000+"

        Returns:
            Dict: JSON containing counts key with counts for each state requested
        """
        counts = 0
        resp = self.query(collections_workflow, state=state, since=since, select='COUNT')
        counts = resp['Count']
        while 'LastEvaluatedKey' in resp:
            resp = self.query(collections_workflow, state=state, since=since, select='COUNT',
                              ExclusiveStartKey=resp['LastEvaluatedKey'])
            counts += resp['Count']
            if limit and counts > limit:
                counts = f"{limit}+"
                break

        return counts

    def get_items_page(self, collections_workflow: str,
                       state: Optional[str]=None, since: Optional[str]=None,
                       limit=100, nextkey: str=None, sort_ascending: Optional[bool]=False,
                       sort_index: Optional[str]=None) -> List[Dict]:
        """Get Items by query

        Args:
            collections_workflow (str): /-separated list of input collections_workflow
            state (Optional[str], optional): State of Items to get (PROCESSING, COMPLETED, FAILED, INVALID)
            since (Optional[str], optional): Get Items since this amount of time in the past. Defaults to None.
            sort_ascending (Optional[bool], optional): Determines which direction the index of the results will be sorted. Defaults to False.
            sort_index (Optional[str], optional): Determines which index to use for sorting, if not applying a filter (state_updated, updated). Defaults to None.

        Returns:
            Dict: List of Items
        """
        items = {
            'items': []
        }
        if nextkey:
            dbitem = self.get_dbitem(nextkey)
            startkey = { key: dbitem[key] for key in ['collections_workflow', 'itemids', 'state_updated', 'updated']}
            resp = self.query(collections_workflow, state=state, since=since, sort_ascending=sort_ascending, sort_index=sort_index, Limit=limit, ExclusiveStartKey=startkey, )
        else:
            resp = self.query(collections_workflow, state=state, since=since,  sort_ascending=sort_ascending, sort_index=sort_index, Limit=limit)
        for i in resp['Items']:
            items['items'].append(self.dbitem_to_item(i))
        if 'LastEvaluatedKey' in resp:
            items['nextkey'] = self.key_to_catid(resp['LastEvaluatedKey'])
        return items

    def get_items(self, *args, limit=None, **kwargs) -> Dict:
        """Get items from database

        Args:
            limit (int, optional): Maximum number of items to return. Defaults to None.

        Returns:
            Dict: StateDB Items
        """
        resp = self.get_items_page(*args, **kwargs)
        items = resp['items']
        while 'nextkey' in resp and (limit is None or len(items) < limit):
            resp = self.get_items_page(*args, nextkey=resp['nextkey'], **kwargs)
            items += resp['items']
        if limit is None or len(items) < limit:
            return items
        return items[:limit]

    def get_state(self, catid: str) -> str:
        """Get current state of Item

        Args:
            catid (str): The catalog ID

        Returns:
            str: Current state: PROCESSING, COMPLETED, FAILED, INVALID
        """
        response = self.table.get_item(Key=self.catid_to_key(catid))
        if 'Item' in response:
            return response['Item']['state_updated'].split('_')[0]
        else:
            # assuming no such item in database
            return ""

    def get_states(self, catids: List[str]) -> Dict[str, str]:
        """Get current state of items

        Args:
            catids (List[str]): List of catalog IDs

        Returns:
            Dict[str, str]: Dictionary of catalog IDs to state
        """
        states = {}
        for dbitem in self.get_dbitems(catids):
            item = self.dbitem_to_item(dbitem)
            states[item['catid']] = item['state']
        return states

    def claim_processing(self, catid):
        """ Sets catid to PROCESSING to claim it (preventing other runs) """
        now = datetime.now(timezone.utc).isoformat()
        key = self.catid_to_key(catid)

        expr = (
            'SET '
            'created = if_not_exists(created, :created), '
            'state_updated=:state_updated, updated=:updated'
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ConditionExpression='NOT begins_with(state_updated, :proc)',
            ExpressionAttributeValues={
                ':created': now,
                ':state_updated': f"PROCESSING_{now}",
                ':updated': now,
                ':proc': "PROCESSING"
            }
        )
        logger.debug("Claimed processing", extra=key)
        return response

    def set_processing(self, catid, execution):
        """ Adds execution to existing item or creates new """
        now = datetime.now(timezone.utc).isoformat()
        key = self.catid_to_key(catid)

        expr = (
            'SET '
            'created = if_not_exists(created, :created), '
            'state_updated=:state_updated, updated=:updated, '
            'executions = list_append(if_not_exists(executions, :empty_list), :exes)'
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ':created': now,
                ':state_updated': f"PROCESSING_{now}",
                ':updated': now,
                ':empty_list': [],
                ':exes': [execution]
            }
        )
        logger.debug("Add execution", extra=key.update({'execution': execution}))
        return response   

    def set_completed(self, catid: str, outputs: List[str]) -> str:
        """Set this catalog as COMPLETED

        Args:
            catid (str): The Cirrus Catalog
            outputs ([str]): List of URLs to output Items

        Returns:
            str: DynamoDB response
        """
        now = datetime.now(timezone.utc).isoformat()
        key = self.catid_to_key(catid)

        expr = (
            'SET '
            'created = if_not_exists(created, :created), '
            'state_updated=:state_updated, updated=:updated, '
            'outputs=:outputs'
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ':created': now,
                ':state_updated': f"COMPLETED_{now}",
                ':updated': now,
                ':outputs': outputs
            }
        )
        logger.debug("set completed", extra=key.update({'outputs': outputs}))
        return response

    def set_failed(self, catid, msg):
        """ Adds new item as failed """
        """ Adds new item with state function execution """
        now = datetime.now(timezone.utc).isoformat()
        key = self.catid_to_key(catid)

        expr = (
            'SET '
            'created = if_not_exists(created, :created), '
            'state_updated=:state_updated, updated=:updated, '
            'last_error=:last_error'
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ':created': now,
                ':state_updated': f"FAILED_{now}",
                ':updated': now,
                ':last_error': msg
            }
        )
        logger.debug("set failed", extra=key.update({'last_error': msg}))
        return response

    def set_invalid(self, catid: str, msg: str) -> str:
        """Set this catalog as INVALID

        Args:
            catid (str): The Cirrus Catalog
            msg (str): An error message to include in DynamoDB Item

        Returns:
            str: DynamoDB response
        """
        now = datetime.now(timezone.utc).isoformat()
        key = self.catid_to_key(catid)

        expr = (
            'SET '
            'created = if_not_exists(created, :created), '
            'state_updated=:state_updated, updated=:updated, '
            'last_error=:last_error'
        )
        response = self.table.update_item(
            Key=key,
            UpdateExpression=expr,
            ExpressionAttributeValues={
                ':created': now,
                ':state_updated': f"INVALID_{now}",
                ':updated': now,
                ':last_error': msg
            }
        )
        logger.debug("set invalid", extra=key.update({'last_error': msg}))
        return response

    def query(self, collections_workflow: str, state: str=None, since: str=None,
              select: str='ALL_ATTRIBUTES', sort_ascending: bool=False, sort_index: str='updated', **kwargs) -> Dict:
        """Perform a single Query on a DynamoDB index

        Args:
            collections_workflow (str): The complete has to query
            state (str, optional): The state of the Item. Defaults to None.
            since (str, optional): Query for items since this time. Defaults to None.
            select (str, optional): DynamoDB Select statement (ALL_ATTRIBUTES, COUNT). Defaults to 'ALL_ATTRIBUTES'.
            sort_ascending (bool, optional): Determines which direction the index of the results will be sorted.
                Defaults to False/Descending.
            sort_index (str, optional): Determines which index to use for sorting, if not applying a filter (default, state_updated, updated)
                If default, sorting will use primary index and sort by item_ids

        Returns:
            Dict: DynamoDB response
        """
        index = None if sort_index == 'default' else sort_index
        

        # always use the hash of the table which is same in all Global Secondary Indices
        expr = Key('collections_workflow').eq(collections_workflow)
        if since:
            start = datetime.now(timezone.utc) - self.since_to_timedelta(since)
            begin = f"{start.isoformat()}"
            end = f"{datetime.now(timezone.utc).isoformat()}"
            if state:
                index = 'state_updated'
                expr = expr & Key(index).between(f"{state}_{begin}", f"{state}_{end}")
            else:
                index = 'updated'
                expr = expr & Key(index).between(begin, end)
        elif state:
            index = 'state_updated'
            expr = expr & Key(index).begins_with(state)

        keys = ['collections_workflow', 'itemids']
        if index:
            keys.append(index)
        if 'ExclusiveStartKey' in kwargs:
            kwargs['ExclusiveStartKey'] = {k: kwargs['ExclusiveStartKey'][k] for k in keys}

        if index:
            resp = self.table.query(IndexName=index, KeyConditionExpression=expr, Select=select, ScanIndexForward=sort_ascending, **kwargs)
        else:
            resp = self.table.query(KeyConditionExpression=expr, Select=select,  ScanIndexForward=sort_ascending, **kwargs)

        return resp

    @classmethod
    def catid_to_key(cls, catid: str) -> Dict:
        """Create DynamoDB Key from catalog ID

        Args:
            catid (str): The catalog ID

        Returns:
            Dict: Dictionary containing the DynamoDB Key
        """
        parts1 = catid.split('/workflow-')
        parts2 = parts1[1].split('/', maxsplit=1)
        key = {
            'collections_workflow': parts1[0] + f"_{parts2[0]}",
            'itemids': '' if len(parts2) == 1 else parts2[1]
        }
        return key

    @classmethod
    def key_to_catid(cls, key: Dict) -> str:
        """Get catalog ID given a DynamoDB Key

        Args:
            key (Dict): DynamoDB Key

        Returns:
            str: Catalog ID
        """
        parts = key['collections_workflow'].rsplit('_', maxsplit=1)
        return f"{parts[0]}/workflow-{parts[1]}/{key['itemids']}"

    @classmethod
    def get_input_catalog_url(self, dbitem):
        catid = self.key_to_catid(dbitem)
        return f"s3://{CATALOG_BUCKET}/{catid}/input.json"

    @classmethod
    def dbitem_to_item(cls, dbitem: Dict, region: str=os.getenv('AWS_REGION', 'us-west-2')) -> Dict:
        state, updated = dbitem['state_updated'].split('_')
        collections, workflow = dbitem['collections_workflow'].rsplit('_', maxsplit=1)
        item = {
            "catid": cls.key_to_catid(dbitem),
            "collections": collections,
            "workflow": workflow,
            "items": dbitem['itemids'],
            "state": state,
            "created": dbitem['created'],
            "updated": dbitem['updated'],
            "catalog": cls.get_input_catalog_url(dbitem)
        }
        if 'executions' in dbitem:
            base_url = f"https://{region}.console.aws.amazon.com/states/home?region={region}#/executions/details/"
            item['executions'] = [base_url + f"{e}" for e in dbitem['executions']]
        if 'outputs' in dbitem:
            item['outputs'] = dbitem['outputs']
        if 'last_error' in dbitem:
            item['last_error'] = dbitem['last_error']
        return item

    @classmethod
    def since_to_timedelta(cls, since: str) -> timedelta:
        """Convert a `since` field to a timedelta.

        Args:
            since (str): Contains an integer followed by a unit letter: 'd' for days, 'h' for hours, 'm' for minutes

        Returns:
            timedelta: [description]
        """
        unit = since[-1]
        # days, hours, or minutes
        assert(unit in ['d', 'h', 'm'])
        days = int(since[0:-1]) if unit == 'd' else 0
        hours = int(since[0:-1]) if unit == 'h' else 0
        minutes = int(since[0:-1]) if unit == 'm' else 0
        return timedelta(days=days, hours=hours, minutes=minutes)
