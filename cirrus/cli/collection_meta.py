import logging

from abc import ABCMeta, abstractmethod
from collections.abc import MutableMapping


logger = logging.getLogger(__name__)


class CollectionMeta(MutableMapping, ABCMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        if 'collection_name' not in attrs:
            attrs['collection_name'] = f'{name.lower()}s'

        if 'collection_display_name' not in attrs:
            attrs['collection_display_name'] = attrs['collection_name'].capitalize()

        if 'enable_cli' not in attrs:
            attrs['enable_cli'] = True

        if not attrs.get('user_extendable', False):
            attrs['user_dir_name'] = None
        elif 'user_dir_name' not in attrs or attrs['user_dir_name'] is None:
            attrs['user_dir_name'] = attrs['collection_name']

        attrs['_elements'] = None
        attrs['project'] = None
        attrs['parent'] = None

        return super().__new__(cls, name, bases, attrs, **kwargs)

    def __hash__(self):
        return hash(self.collection_name)

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
                f'No cirrus project specified; limited to built-in {self.collection_display_name}.',
            )
            return None
        return self.project.path.joinpath(self.user_dir_name)

    def get_search_dirs(self):
        user_dir = self.user_dir
        if user_dir and user_dir.is_dir():
            return [self.user_dir]
        else:
            return None

    @abstractmethod
    def find(self):
        pass

    def reset_elements(self):
        self._elements = None

    def register_project(self, project):
        self.project = project
        self.reset_elements()

    def items(self):
        return self.elements.items()

    def keys(self):
        return self.elements.keys()

    def values(self):
        return self.elements.values()

    def __iter__(self):
        return iter(self.elements)

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
