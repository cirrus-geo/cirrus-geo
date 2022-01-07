import logging

from .base import ComponentFile


logger = logging.getLogger(__name__)


default_handler = '''#!/usr/bin/env python
from cirrus.lib.process_payload import ProcessPayload
from cirrus.lib.logging import get_task_logger


LAMBDA_TYPE = '{component_type}'


def lambda_handler(event, context={{}}):
    payload = ProcessPayload.from_event(event)
    logger = get_task_logger(f'{{LAMBDA_TYPE}}.{name}', payload=payload)
    return payload
'''.format


class PythonHandler(ComponentFile):
    def __init__(self, *args, name='lambda_function.py', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        return default_handler(component_type=component.type, name=component.name)
