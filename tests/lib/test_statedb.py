# import moto before any boto3 module
from moto import mock_dynamodb2
import boto3
import inspect
import json
import os
import pytest
import unittest

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from cirrus.lib.statedb import StateDB, STATES

## fixtures
testpath = os.path.dirname(__file__)
table_name = 'cirrus-test-state'
test_dbitem = {
    'collections_workflow': 'col1_wf1',
    'itemids': 'item1/item2',
    'state_updated': f"QUEUED_{datetime.now()}",
    'created': datetime.now(),
    'updated': datetime.now()
}
test_item = {
    "id": "col1/workflow-wf1/item1/item2",
    "process": {
        "output_options": {
            "collections": {
                "output-collection": ".*"
            }
        }
    }
}

@mock_dynamodb2
def setup_table():
    boto3.setup_default_session()
    client = boto3.resource('dynamodb')
    with open(os.path.join(testpath, 'statedb_schema.json')) as f:
        schema = json.loads(f.read())
    table = client.create_table(**schema)
    table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
    return StateDB(table_name)


class TestClassMethods(unittest.TestCase):

    testkey = {
        'collections_workflow': 'col1_wf1',
        'itemids': 'item1/item2'
    }

    def test_catid_to_key(self):
        key = StateDB.catid_to_key(test_item['id'])
        assert(key['collections_workflow'] == "col1_wf1")
        assert(key['itemids'] == 'item1/item2')

    def test_key_to_catid(self):
        catid = StateDB.key_to_catid(self.testkey)
        assert(catid == test_item['id'])

    def test_get_input_catalog_url(self):
        url = StateDB.get_input_catalog_url(self.testkey)
        assert(f"{test_item['id']}/input.json" in url)

    def test_dbitem_to_item(self):
        item = StateDB.dbitem_to_item(test_dbitem)
        assert(item['catid'] == test_item['id'])
        assert(item['workflow'] == 'wf1')
        assert(item['state'] == 'QUEUED')

    def test_since_to_timedelta(self):
        td = StateDB.since_to_timedelta('1d')
        assert(td.days == 1)
        td = StateDB.since_to_timedelta('1h')
        assert(td.seconds == 3600)
        td = StateDB.since_to_timedelta('10m')
        assert(td.seconds == 600)


class TestDbItems(unittest.TestCase):

    nitems = 1000

    @classmethod
    def setUpClass(cls):
        cls.mock = mock_dynamodb2()
        cls.mock.start()
        cls.statedb = setup_table()
        for i in range(cls.nitems):
            newitem = deepcopy(test_item)
            cls.statedb.set_processing(newitem['id'] + str(i), execution='arn::test')
        cls.statedb.set_processing(test_item['id'] + '_processing', execution='arn::test')
        cls.statedb.set_completed(test_item['id'] + '_completed', outputs=['item1', 'item2'])
        cls.statedb.set_failed(test_item['id'] + '_failed', 'failed')
        cls.statedb.set_invalid(test_item['id'] + '_invalid', 'invalid')


    @classmethod
    def tearDownClass(cls):
        for i in range(cls.nitems):
            cls.statedb.delete_item(test_item['id'] + str(i))
        for s in STATES:
            cls.statedb.delete_item(test_item['id'] + f"_{s.lower()}")
        cls.statedb.delete()
        cls.mock.stop()

    def test_set_processing(self):
        resp = self.statedb.set_processing(test_item['id'], execution='arn::test1')
        assert(resp['ResponseMetadata']['HTTPStatusCode'] == 200)
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(StateDB.key_to_catid(dbitem) == test_item['id'])
        assert(dbitem['executions'] == ['arn::test1'])

        # check that processing adds new execution to list
        resp = self.statedb.set_processing(test_item['id'], execution='arn::test2')
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(len(dbitem['executions']) == 2)
        assert(dbitem['executions'][-1] == 'arn::test2')
        self.statedb.delete_item(test_item['id'])
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem is None)

    def test_get_dbitem(self):
        dbitem = self.statedb.get_dbitem(test_item['id'] + '0')
        assert(dbitem['itemids'] == test_dbitem['itemids'] + '0')
        assert(dbitem['collections_workflow'] == test_dbitem['collections_workflow'])
        assert(dbitem['state_updated'].startswith('PROCESSING'))

    def test_get_dbitem_noitem(self):
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem is None)

    def test_get_dbitems(self):
        ids = [test_item['id'] + str(i) for i in range(10)]
        dbitems = self.statedb.get_dbitems(ids)
        assert(len(dbitems) == len(ids))
        for dbitem in dbitems:
            assert(self.statedb.key_to_catid(dbitem) in ids)

    def test_get_dbitems_noitems(self):
        #with self.assertRaises(Exception):
        dbitems = self.statedb.get_dbitems([test_item['id']])
        assert(len(dbitems) == 0)

    def test_get_items(self):
        items = self.statedb.get_items(test_dbitem['collections_workflow'], state='PROCESSING', since='1h')
        assert(len(items) == self.nitems + 1)
        items = self.statedb.get_items(test_dbitem['collections_workflow'], state='PROCESSING', since='1h', limit=1)
        assert(len(items) == 1)

    def test_get_state(self):
        for s in STATES:
            state = self.statedb.get_state(test_item['id'] + f"_{s.lower()}")
            assert(state == s)
        state = self.statedb.get_state(test_item['id'] + 'nosuchitem')

    def test_get_states(self):
        ids = [test_item['id'] + f"_{s.lower()}" for s in STATES]
        states = self.statedb.get_states(ids)
        assert(len(ids) == len(states))
        for i, id in enumerate(ids):
            assert(states[id] == STATES[i])

    def test_set_processing(self):
        resp = self.statedb.set_processing(test_item['id'], execution='testarn')
        assert(resp['ResponseMetadata']['HTTPStatusCode'] == 200)
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem['state_updated'].startswith('PROCESSING'))
        assert(dbitem['executions'] == ['testarn'])

    def test_set_outputs(self):
        resp = self.statedb.set_completed(test_item['id'], outputs=['output-item'])
        assert(resp['ResponseMetadata']['HTTPStatusCode'] == 200)
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem['outputs'][0] == 'output-item')

    def test_set_completed(self):
        resp = self.statedb.set_completed(test_item['id'])
        assert(resp['ResponseMetadata']['HTTPStatusCode'] == 200)
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem['state_updated'].startswith('COMPLETED'))

    def test_set_failed(self):
        resp = self.statedb.set_failed(test_item['id'], msg='test failure')
        assert(resp['ResponseMetadata']['HTTPStatusCode'] == 200)
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem['state_updated'].startswith('FAILED'))
        assert(dbitem['last_error'] == 'test failure')

    def test_set_completed_with_outputs(self):
        resp = self.statedb.set_completed(test_item['id'], outputs=['output-item2'])
        assert(resp['ResponseMetadata']['HTTPStatusCode'] == 200)
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem['state_updated'].startswith('COMPLETED'))
        assert(dbitem['outputs'][0] == 'output-item2')

    def test_set_invalid(self):
        resp = self.statedb.set_invalid(test_item['id'], msg='test failure')
        assert(resp['ResponseMetadata']['HTTPStatusCode'] == 200)
        dbitem = self.statedb.get_dbitem(test_item['id'])
        assert(dbitem['state_updated'].startswith('INVALID'))
        assert(dbitem['last_error'] == 'test failure')

    def test_get_counts(self):
        count = self.statedb.get_counts(test_dbitem['collections_workflow'])
        assert(count == self.nitems + 4)
        for s in STATES:
            count = self.statedb.get_counts(test_dbitem['collections_workflow'], state=s)
            if s == 'PROCESSING':
                assert(count == self.nitems + 1)
            else:
                assert(count == 1)
        count = self.statedb.get_counts(test_dbitem['collections_workflow'], since='1h')


    def _test_get_counts_paging(self):
        for i in range(5000):
            self.statedb.set_processing(test_item['id'] + f"_{i}", execution='arn::test')
        count = self.statedb.get_counts(test_dbitem['collections_workflow'])
        assert(count == 1004)
        for i in range(5000):
            self.statedb.delete_item(test_item['id'] + f"_{i}")
