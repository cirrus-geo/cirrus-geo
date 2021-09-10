import logging

from .base import ComponentFile


logger = logging.getLogger(__name__)


default_handler = '''#!/usr/bin/env python
from cirruslib import Catalog, get_task_logger


def handler(payload, context={{}}):
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger(f"{{__name__}}.{name}", catalog=catalog)
    return catalog
'''.format


class PythonHandler(ComponentFile):
    def __init__(self, *args, name='handler.py', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        return default_handler(name=component.name)
