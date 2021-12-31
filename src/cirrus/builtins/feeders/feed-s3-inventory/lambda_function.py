import argparse
import boto3
import gzip
import json
import io
import logging
import re
import sys
from datetime import datetime
from dateutil.parser import parse
from os import getenv, path as op

import pyorc
from boto3utils import s3
from cirrus.lib.utils import submit_batch_job


# envvars
SNS_TOPIC = getenv('CIRRUS_PROCESS_TOPIC_ARN')

# clients
SNS_CLIENT = boto3.client('sns')

# logging
logger = logging.getLogger("feeder.s3-inventory")


def read_orc_inventory_file(filename, keys):
    with open(filename, "rb") as data:
        reader = pyorc.Reader(data)
        for row in reader:
            record = {keys[i].lower(): v for i, v in enumerate(row)}
            yield record


def read_csv_inventory_file(filename, keys):
    gz = gzip.open(filename, 'rb')
    for line in io.BufferedReader(gz):
        line = line.decode('utf-8').replace('"', '').replace('\n', '')
        record = {keys[i].lower(): v for i, v in enumerate(line.split(','))}
        yield record
    gz.close()


def read_inventory_file(fname, keys, prefix=None, suffix=None,
                        start_date=None, end_date=None,
                        datetime_regex=None, datetime_key='LastModifiedDate'):
    logger.debug('Reading inventory file %s', fname)
    filename = s3().download(fname, path='/tmp')
    ext = op.splitext(fname)[-1]
    if ext == ".gz":
        records = read_csv_inventory_file(filename, keys)
    elif ext == ".orc":
        records = read_orc_inventory_file(filename, keys)

    if datetime_regex is not None:
        regex = re.compile(datetime_regex)
    else:
        regex = None

    sdate = parse(start_date).date() if start_date else None
    edate = parse(end_date).date() if end_date else None

    def get_datetime(record):
        if regex is not None:
            m = regex.match(record['key']).groupdict()
            dt = datetime(int(m['Y']), int(m['m']), int(m['d']))
        elif isinstance(record[datetime_key], datetime.datetime):
            dt = record[datetime_key]
        else:
            dt = datetime.strptime(record[datetime_key], "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.date()

    for record in records:
        if prefix is not None and not record['key'].startswith(prefix):
            continue

        if suffix is not None and not record['key'].endswith(suffix):
            continue

        if sdate is not None:
            dt = get_datetime(record)
            if dt < sdate:
                continue

        if edate is not None:
            dt = get_datetime(record)
            if dt > edate:
                continue

        # made it here without getting filtered out
        yield 's3://%s/%s' % (record['bucket'], record['key'])


def lambda_handler(payload, context={}):
    logger.info('Payload: %s', json.dumps(payload))

    # get payload variables
    inventory_url = payload.pop('inventory_url', None)
    batch_size = payload.pop('batch_size', 10)
    max_batches = payload.pop('max_batches', -1)
    # required payload variable
    process = payload.pop('process')

    s3session = s3()

    # get latest inventory manifest and spawn batches (this currently assumes being run as Lambda!)
    if inventory_url is not None:
        inventory_bucket = s3session.urlparse(inventory_url)['bucket']
        # get manifest and schema
        manifest = s3session.latest_inventory_manifest(inventory_url)
        schema = manifest['fileSchema']
        if schema.startswith('struct'):
            keys = [str(key).strip().split(':')[0] for key in schema[7:-1].split(',')]
        else:
            keys = [str(key).strip() for key in schema.split(',')]

        # get list of inventory files
        files = manifest.get('files')
        logger.info(
            'Getting latest inventory (%s files) from %s',
            len(files),
            inventory_url,
        )

        submitted_urls = []
        njobs = 0
        for f in files:
            url = f"s3://{inventory_bucket}/{f['key']}"
            submitted_urls.append(url)
            if (len(submitted_urls) % batch_size) == 0:
                batch_payload = {
                    'inventory_files': submitted_urls,
                    'keys': keys,
                    'process': process
                }
                batch_payload.update(payload)
                submit_batch_job(
                    batch_payload,
                    context.invoked_function_arn,
                    definition='lambda-as-batch',
                    name='feed-s3-inventory',
                )
                submitted_urls = []
                njobs += 1
                # stop if max batches reached (used for testing)
                if max_batches > 0 and njobs >= max_batches:
                    break
        if len(submitted_urls) > 0:
            batch_payload = {
                'inventory_files': submitted_urls,
                'keys': keys,
                'process': process
            }
            batch_payload.update(payload)
            submit_batch_job(
                batch_payload,
                context.invoked_function_arn,
                definition='lambda-as-batch',
                name='feed-s3-inventory',
            )
            njobs += 1
        logger.info("Submitted %s batch jobs", njobs)
        return njobs

    # process inventory files (assumes this is batch!)
    inventory_files = payload.pop('inventory_files', None)
    keys = payload.pop('keys', None)
    base_url = payload.pop('base_url', None)

    # these are all required
    payload_ids = []
    if inventory_files and keys and process:
        # filter filenames
        logger.info("Parsing %s inventory files", len(inventory_files))
        for f in inventory_files:
            for url in read_inventory_file(f, keys, **payload):
                parts = s3session.urlparse(url)
                id = '-'.join(op.dirname(parts['key']).split('/'))

                # use extension without . for asset key
                ext = op.splitext(parts['key'])[-1].lstrip('.')

                if base_url is not None and url.startswith('s3://'):
                    url = f"{base_url}/{parts['bucket']}/{parts['key']}"

                # TODO - determime input collection from url
                item = {
                    'type': 'Feature',
                    'id': id,
                    'collection': process['input_collections'][0],
                    'properties': {},
                    'assets': {
                        ext: {
                            'href': url
                        }
                    }
                }
                payload = {
                    'type': 'FeatureCollection',
                    'features': [item],
                    'process': process
                }

                # feed to cirrus through SNS topic
                SNS_CLIENT.publish(
                    TopicArn=SNS_TOPIC,
                    Message=json.dumps(payload),
                )
                if (len(payload_ids) % 1000) == 0:
                    logger.debug(
                        "Published %s payloads to %s: %s",
                        len(payload_ids),
                        SNS_TOPIC,
                        json.dumps(payload),
                    )

                payload_ids.append(item['id'])

        logger.info(
            "Published %s payloads from %s inventory files",
            len(payload_ids),
            len(inventory_files),
        )
        return payload_ids


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # argparse
    parser = argparse.ArgumentParser(description='feeder')
    parser.add_argument('payload', help='Payload file')
    args = parser.parse_args(sys.argv[1:])

    with open(args.payload) as f:
        payload = json.loads(f.read())
    lambda_handler(payload)
