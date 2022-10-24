import copy
from collections.abc import MutableMapping, MutableSequence
from pathlib import Path

import yaml
from cfn_flip import yaml_dumper
from cfn_tools import odict, yaml_loader

from . import pseudo_parameters


def _yamlable_representer(dumper, data):
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items()
    )


class YamlableList(MutableSequence):
    def __init__(self, *args):
        self.list = list()
        self.extend(list(args))

    def _convert(self, val):
        if isinstance(val, dict):
            return NamedYamlable(val)
        elif isinstance(val, list):
            return type(self)(*val)
        else:
            return pseudo_parameters.replace_pseudo_params_with_sub(
                None,
                val,
            )

    def __len__(self):
        return len(self.list)

    def __getitem__(self, index):
        return self.list[index]

    def __delitem__(self, index):
        del self.list[index]

    def __setitem__(self, index, val):
        self.list[index] = self._convert(val)

    def insert(self, index, val):
        self.list.insert(index, self._convert(val))

    def __str__(self):
        return str(self.list)

    def __repr__(self):
        return str(self.list)

    def __add__(self, other):
        return self.list + other


class NamedYamlableMeta(type(MutableMapping)):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        yaml_dumper.CfnYamlDumper.add_representer(self, _yamlable_representer)


class NamedYamlable(MutableMapping, metaclass=NamedYamlableMeta):
    _dict_type = odict.ODict

    # FUTURE: once not supporting py versions <3.8,
    # use the '/' version of this signature
    # def __init__(self, dict=None, /, **kwargs):
    def __init__(self, dict=None, **kwargs):
        self._dict = type(self)._dict_type()
        if dict is not None:
            self.update(dict)
        if kwargs:
            self.update(kwargs)
        self.validate()

    @classmethod
    def from_yaml(cls, yml: str):
        return cls(yaml.load(yml, Loader=yaml_loader.CfnYamlLoader))

    @classmethod
    def from_file(cls, f: Path):
        return cls.from_yaml(f.read_text(encoding="utf-8"))

    def validate(self) -> None:
        pass

    def _dump(
        self, *args, clean_up: bool = True, long_form: bool = True, **kwargs
    ) -> str:
        return yaml.dump(
            self._dict,
            *args,
            Dumper=yaml_dumper.get_dumper(clean_up=clean_up, long_form=long_form),
            **kwargs,
        )

    def to_yaml(self) -> str:
        return self._dump()

    def to_file(self, f: Path) -> None:
        with f.open("w") as f:
            self._dump(stream=f)

    def copy(self):
        return copy.deepcopy(self)

    # make this work like a namespace for keys that
    # are in a format compatible with python identifiers
    def __setattr__(self, name, val):
        if name == "_dict":
            return super().__setattr__(name, val)
        if isinstance(val, dict):
            self._dict[name] = NamedYamlable(val)
        elif isinstance(val, list):
            self._dict[name] = YamlableList(*val)
        else:
            self._dict[name] = pseudo_parameters.replace_pseudo_params_with_sub(
                name,
                val,
            )

    def __getattr__(self, name):
        if name == "_dict":
            return super().__getattr__(name)
        try:
            return self._dict[name]
        except KeyError:
            cls = type(self)
            raise AttributeError(
                f"'{cls.__module__}.{cls.__qualname__}' object has no attribute '{name}'",
            ) from None

    # dict methods to make this look
    # like a dict and quack like a dict
    def __len__(self):
        return len(self._dict)

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, val):
        self.__setattr__(key, val)

    def __delitem__(self, key):
        del self._dict[key]

    def __iter__(self):
        return iter(self._dict)

    def __repr__(self):
        return f"{type(self).__qualname__}({repr(self._dict)})"

    def __or__(self, other):
        new = self.copy()
        new.update(other)
        return new

    def __ior__(self, other):
        self.update(other)

    def items(self):
        return self._dict.items()


def _construct_yamlable(loader, node, deep=False):
    loader.flatten_mapping(node)
    yamlable = NamedYamlable()
    for key_node, val_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        val = loader.construct_object(val_node, deep=deep)
        yamlable[key] = val
    return yamlable


def _construct_yamlablelist(loader, node, deep=False):
    return YamlableList(
        *[loader.construct_object(val, deep=deep) for val in node.value]
    )


def _yamlablelist_representer(dumper, data):
    return dumper.represent_sequence(
        yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, data
    )


yaml_dumper.CfnYamlDumper.add_representer(YamlableList, _yamlablelist_representer)
yaml_loader.CfnYamlLoader.add_constructor(yaml_loader.TAG_MAP, _construct_yamlable)
yaml_loader.CfnYamlLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG,
    _construct_yamlablelist,
)
