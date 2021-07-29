import os
import yaml

from pathlib import Path
from types import SimpleNamespace

from cirrus.cli.exceptions import ConfigError


DEFAULT_CONFIG = {
    'backend': 'serverless',
    'sources': {
        'feeders': ['./feeders'],
        'tasks': ['./tasks'],
        'workflows': ['./workflows'],
    },
}


class NestedNamespace(SimpleNamespace):
    def __init__(self, d: dict, **kwargs):
        super().__init__(**kwargs)
        self._convert_dict(d)

    def _convert_dict(self, d: dict):
        for key, val in d.items():
            key = str(key)
            if isinstance(val, dict):
                self.__setattr__(key, NestedNamespace(val))
            elif isinstance(val, list):
                self.__setattr__(key, list(self._convert_list(val)))
            else:
                self.__setattr__(key, val)

    def _convert_list(self, l: list):
        for item in l:
            if isinstance(item, dict):
                yield NestedNamespace(item)
            elif isinstance(item, list):
                yield self._convert_list(item)
            else:
                yield item

    def __repr__(self):
        return self.__dict__.__repr__()


class Config(NestedNamespace):
    def __init__(self, conf: dict):
        # TODO: validation and setting required keys if missing
        super().__init__(conf)

    @classmethod
    def from_yaml(cls, yml: str):
        return cls(yaml.safe_load(yml))

    @classmethod
    def from_file(cls, f: Path):
        return cls.from_yaml(f.read_text(encoding='utf-8'))

    def __repr__(self):
        return 'Config{}'.format(self.__dict__.__repr__())
