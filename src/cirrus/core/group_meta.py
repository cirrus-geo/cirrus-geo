import logging

from abc import ABCMeta, abstractmethod
from collections.abc import MutableMapping
from pathlib import Path

import cirrus.builtins

from cirrus.core.utils.plugins import iter_resources


logger = logging.getLogger(__name__)


def resource_plugins(resource_type):
    plugins = {}
    for entrypoint in iter_resources():
        plugin_path = Path(entrypoint.load().__path__[0]).joinpath(resource_type)

        if not plugin_path.is_dir():
            continue

        plugins[entrypoint.name] = plugin_path

    return plugins


class GroupMeta(MutableMapping, ABCMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        if 'group_name' not in attrs:
            attrs['group_name'] = f'{name.lower()}s'

        if 'group_display_name' not in attrs:
            attrs['group_display_name'] = attrs['group_name'].capitalize()

        if 'enable_cli' not in attrs:
            attrs['enable_cli'] = True

        if 'cmd_aliases' not in attrs:
            attrs['cmd_aliases'] = []

        attrs['user_extendable'] = attrs.get('user_extendable', False)

        if not attrs['user_extendable']:
            attrs['user_dir_name'] = None
        elif 'user_dir_name' not in attrs or attrs['user_dir_name'] is None:
            attrs['user_dir_name'] = attrs['group_name']

        attrs['_plugins'] = None
        attrs['_elements'] = None
        attrs['project'] = None
        attrs['parent'] = None

        return super().__new__(cls, name, bases, attrs, **kwargs)

    @classmethod
    def __subclasshook__(cls, C):
        if cls is GroupMeta:
            if any("elements" in B.__dict__ for B in C.__mro__):
                return True
            return False
        return NotImplemented

    def __hash__(self):
        return hash(self.group_name)

    @property
    def plugins(self):
        if self._plugins is None:
            self._plugins = (
                resource_plugins(self.group_name)
                if self.user_extendable
                else {}
            )
        return self._plugins

    @property
    def elements(self):
        if self._elements is None:
            self.find()
        return self._elements

    @property
    def user_dir(self):
        if self.user_dir_name is None:
            return None
        if self.project is None or self.project.path is None:
            logger.warning(
                f'No cirrus project specified; limited to {self.group_display_name} built-in and from plugins.',
            )
            return None
        return self.project.path.joinpath(self.user_dir_name)

    @abstractmethod
    def find(self):
        pass

    def reset_elements(self):
        self._elements = None

    def register_parent(self, parent):
        self.parent = parent

    def register_project(self, project):
        self.project = project
        self.reset_elements()

    def create_user_dir(self):
        '''Used on project init to create any default files.
        Useful for things that most projects require but shouldn't
        be managed by default by cirrus, e.g., cloudformation templates
        for S3 buckets.'''
        self.user_dir.mkdir(exist_ok=True)

    def ensure_created(self):
        if not (self.user_extendable and self.user_dir):
            return False
        self.create_user_dir()

    def items(self):
        return self.elements.items()

    def keys(self):
        return self.elements.keys()

    def values(self):
        return self.elements.values()

    def __iter__(self):
        return iter(self.elements.values())

    def __len__(self):
        return len(self.elements)

    def __getitem__(self, key):
        return self.elements[key]

    def __setitem__(self, key, val):
        self.elements[key] = val

    def __delitem__(self, key):
        del self.elements[key]

    def __repr__(self):
        return f'{type(self).__qualname__}({repr(self.elements)})'
