from cirruslib import Catalog


def handler(payload, context):
    catalog = Catalog.from_payload(payload)
    return catalog
