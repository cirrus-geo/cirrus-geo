from cirruslib import Catalog


def lambda_handler(payload, context):
    catalog = Catalog.from_payload(payload)
    return catalog
