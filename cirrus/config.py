import os
import yaml

from types import SimpleNamespace

from cirrus.exceptions import ConfigError


CONFIG_VAR = 'CIRRUS_SETTINGS_YAML'


DEFAULT_CONFIG = {
    'backend': 'serverless',
    'sources': {
        'feeders': [],
        'tasks': [],
        'workflows': [],
    },
}


DEFAULT_CONFIG_YML = '''
backend: serverless
feeders:
  sources:
    - ./feeders/
tasks:
  sources:
    - ./tasks/
workflows:
  sources:
    - ./workflows
'''


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

    def __repr__(self):
        return 'Config{}'.format(self.__dict__.__repr__())


# Inspired by Django settings
class LazyConfig:
    def __init__(self):
        self._wrapped = None

    def _load_config(self):
        config = os.environ.get(CONFIG_VAR)
        if not config:
            raise ConfigError(
                "No configuration defined. "
                f"Set the environment variable '{CONFIG_VAR}' before accessing config."
            )

        with open(config) as f:
            self._wrapped = Config.from_yaml(f.read())


    def __repr__(self):
        name = self.__class__.__name__
        if self._wrapped is None:
            return f'<{name} [Not Loaded]>'
        return self._wrapped.__repr__()

    def __getattr__(self, name: str):
        if name == '_wrapped':
            return super().__getattr__(name)
        if self._wrapped is None:
            self._load_config()
        return getattr(self._wrapped, name)

    def __setattr__(self, name: str, val):
        if name == '_wrapped':
            return super().__setattr__(name, val)
        if self._wrapped is None:
            self._load_config()
        return setattr(self._wrapped, name)


config = LazyConfig()


if __name__ == '__main__':
    DEFAULT_CONFIG['sources']['feeders'].append('a/b/c/d')
    DEFAULT_CONFIG['sources']['feeders'].append({1:2, 3:4})

    # see not loaded
    print(config)

    # try to access without config set
    # and confirm we get an exception
    os.environ.pop(CONFIG_VAR, None)
    try:
        print(config.sources)
    except ConfigError as e:
        print(e)

    # set config to default dict
    config._wrapped = Config(DEFAULT_CONFIG)

    # see the whole config object
    print(config)

    # access part of the config
    print(config.sources.feeders)
