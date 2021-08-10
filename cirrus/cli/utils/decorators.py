import sys
import logging

from functools import wraps
from cirrus.cli.project import project


logger = logging.getLogger(__name__)


def requires_project(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if project._path is None:
            logger.error('Fatal: no cirrus project detected/specified.')
            sys.exit(1)
        return func(*args, **kwargs)
    return wrapper
