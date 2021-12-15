import logging

from .base import ComponentFile


logger = logging.getLogger(__name__)


default_handler = '''#!/usr/bin/env python
from cirruslib import Catalog, get_task_logger


LAMBDA_TYPE = '{component_type}'


def lambda_handler(payload, context={{}}):
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger(f'{{LAMBDA_TYPE}}.{name}', catalog=catalog)
    return catalog
'''.format


class PythonHandler(ComponentFile):
    def __init__(self, *args, name='lambda_function.py', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        return default_handler(component_type=component.type, name=component.name)
