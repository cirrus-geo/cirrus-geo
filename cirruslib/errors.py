import importlib
import sys

module = __name__.split('.')[-1]
sys.modules[__name__] = importlib.import_module(f'cirrus.lib.{module}')