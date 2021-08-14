import sys
import logging

from typing import Type, TypeVar
from abc import ABCMeta
from pathlib import Path

from cirrus.cli.exceptions import ComponentError
from cirrus.cli.project import project


logger = logging.getLogger(__name__)


T = TypeVar('T', bound='Component')
class ComponentMeta(ABCMeta):
    registered_component_types_plural = {}
    registered_component_types = {}

    def __new__(cls, name, bases, attrs, **kwargs):
        if not 'abstract' in attrs:
            attrs['abstract'] = False
        return super().__new__(cls, name, bases, attrs, **kwargs)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.component_type=self.__name__.lower()
        self.plural_name = f'{self.component_type}s'
        self.default_user_dir_name = self.plural_name
        self.core_dir = Path(sys.modules[self.__module__].__file__,).parent.joinpath('config')

        if not self.abstract:
            self.registered_component_types_plural[self.plural_name] = self
            self.registered_component_types[self.component_type] = self

    @property
    def default_user_dir(self):
        if self.user_extendable:
            try:
                return project.path_safe.joinpath(self.default_user_dir_name)
            except AttributeError:
                pass
        return None

    def resolve_component_type_plural(self, plural_component_type: str):
        try:
            return self.registered_component_types_plural[component_type]
        except KeyError:
            raise ValueError(f"Unknown component type: '{plural_component_type}'")

    def resolve_component_type(self, component_type: str):
        try:
            return self.registered_component_types[component_type]
        except KeyError:
            raise ValueError(f"Unknown component type: '{component_type}'")

    def resolve_component(self, component_type: str, component_name: str) -> Type[T]:
        component_type = self.resolve_component_type(component_type)
        component = component_type.find_first(component_name)
        if not component:
            raise ValueError(f"Unknown {component_type.component_type}: '{component_name}'")
        return component


class Component(metaclass=ComponentMeta):
    abstract = True
    enable_cli = True
    user_extendable = True

    def __init__(self, path: Path, load: bool=True) -> None:
        self.path = path
        self.name = path.name
        self.files = []
        self.config = None
        self.description = ''
        self.is_core_component = self.path.parent.samefile(self.__class__.core_dir)
        self._loaded = False
        if load:
            self._load()

    @property
    def display_name(self):
        return '{}{}'.format(
            self.name,
            ' (built-in)' if self.is_core_component else '',
        )

    def _load(self, init_components=False):
        if not self.path.is_dir():
            raise ComponentError(
                f"Cannot load {self.component_type} from '{self.path}': not a directory."
            )

        for attr, val in self.__class__.__dict__.items():
            if hasattr(val, 'copy_to_component'):
                if init_components:
                    val.init(self)
                val.copy_to_component(self, attr)

        self.load_config()
        self._loaded = True

    def load_config(self):
        pass

    def _create(self):
        if self._loaded:
            raise ComponentError(f'Cannot create a loaded {self.__class__.__name__}.')
        try:
            self.path.mkdir()
        except FileExistsError as e:
            raise ComponentError(
                f"Cannot create {self.__class__.__name__} at '{self.path}': already exists."
            ) from e
        self._load(init_components=True)

    @classmethod
    def create(cls, name: str) -> Type[T]:
        if not cls.user_extendable:
            raise ComponentError(
                f"Component {self.component_type} does not support creation"
            )
        path = cls.default_user_dir.joinpath(name)
        new = cls(path, load=False)
        new._create()
        return new

    @classmethod
    def from_dir(cls, d: Path, name: str=None) -> Type[T]:
        for component_dir in d.resolve().iterdir():
            if name and component_dir.name != name:
                continue
            try:
                yield cls(component_dir)
            except ComponentError:
                logger.debug(
                    f"Directory does not appear to be a {cls.component_type}, skipping: '{component_dir}'",
                )
                continue

    @classmethod
    def find(cls, name: str=None) -> Type[T]:
        # search user dir first, as we prefer a user
        # implementation if a component name is specified
        search_dirs = []

        user_dir = cls.default_user_dir
        if user_dir is not None:
            search_dirs.append(user_dir)

        search_dirs.append(cls.core_dir)

        for _dir in search_dirs:
            yield from cls.from_dir(_dir, name=name)

    @classmethod
    def find_first(cls, name: str) -> Type[T]:
        try:
            return next(cls.find(name=name))
        except StopIteration:
            return None
