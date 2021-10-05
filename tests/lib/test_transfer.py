# import moto before any boto3 module
from moto import mock_s3, mock_secretsmanager
import boto3
import os
import unittest

from boto3utils import s3
from cirrus.lib import transfer
from shutil import rmtree

testpath = f"{os.path.dirname(__file__)}/test_transfer"
testbucket = 'testbucket'

@mock_s3
@mock_secretsmanager
class Test(unittest.TestCase):

    def setUp(self):
        session = boto3.session.Session(region_name='us-east-1')
        client = s3(session)
        client.s3.create_bucket(Bucket=testbucket)
        client.s3.put_object(Body='test', Bucket=testbucket, Key=os.path.basename(__file__))
        os.makedirs(testpath, exist_ok=True)
        #client.upload_file(Filename=os.path.join(testpath, 'test.json'), Bucket=testbucket, Key='test.json')
        #yield client

    @classmethod
    def tearDownClass(cls):
        rmtree(testpath)

    def get_test_item(self):
        item = {
            'id': 'test-item',
            'collection': 'test-collection',
            'assets': {
                'local': {
                    'href': __file__
                },
                'remote': {
                    'href': f"s3://{testbucket}/{os.path.basename(__file__)}"
                }
            }
        }
        return item

    def test_get_s3_session(self):
        session = transfer.get_s3_session(region_name='us-west-2')
        buckets = session.s3.list_buckets()
        assert(buckets['Buckets'][0]['Name'] == testbucket)

    def _test_download_from_http(self):
        url = 'https://raw.githubusercontent.com/cirrus-geo/cirrus/master/README.md'
        fname = transfer.download_from_http(url, path=testpath)
        assert(os.path.exists(fname))
        with open(fname) as f:
            lines = f.readlines()
        assert('Cirrus') in lines[0]

    def test_download_item_assets(self):
        item = self.get_test_item()
        new_item = transfer.download_item_assets(item, path=testpath)
        for k in new_item['assets']:
            assert(os.path.exists(new_item['assets'][k]['href']))

    def test_upload_item_assets(self):
        item = self.get_test_item()
        path_template = 's3://testbucket/${id}/test'
        assets = ['local']
        new_item = transfer.upload_item_assets(item, assets=assets, path_template=path_template, s3_urls=True, region_name='us-west-2')
        for k in assets:
            assert(new_item['assets'][k]['href'].startswith('s3://'))
            assert(s3().exists(new_item['assets'][k]['href']))

    def test_get_path(self):
        path_template = 's3://testbucket/${collection}/${id}'
        item = self.get_test_item()
        path = transfer.get_path(self.get_test_item(), template = path_template)
        assert(path == f"s3://{testbucket}/{item['collection']}/{item['id']}")
