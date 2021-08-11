import sys
import copy
import logging

from typing import Type, TypeVar, Callable
from abc import ABCMeta
from pathlib import Path

from cirrus.cli.exceptions import CirrusError, ComponentError
from cirrus.cli.project import project
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


registered_component_types_plural = {}
registered_component_types = {}


class ComponentMeta(ABCMeta):
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
            registered_component_types_plural[self.plural_name] = self
            registered_component_types[self.component_type] = self

    @property
    def default_user_dir(self):
        if self.user_extendable:
            try:
                return project.path_safe.joinpath(self.default_user_dir_name)
            except AttributeError:
                pass
        return None


T = TypeVar('T', bound='ComponentBase')
class ComponentBase(metaclass=ComponentMeta):
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


T = TypeVar('T', bound='ComponentFile')
class ComponentFile:
    def __init__(
        self,
        filename:
        str=None,
        optional: bool=False,
        content_fn: Callable[[Type[ComponentBase]], str]=None,
    ) -> None:
        self.filename = filename
        self.required = not optional
        self.content_fn = content_fn
        self._content = None

        if self.required and not self.content_fn:
            raise ValueError('Required files must have a content_fn defined.')

    @property
    def content(self):
        if self._content is None:
            try:
                self._content = self.path.read_text()
            except FileNotFoundError as e:
                if self.required:
                    raise ComponentError(
                            f"{self.__class__.__name__} at '{self.path}': unable to open for read"
                    ) from e
                else:
                    # log something about defaulting content to None
                    self._content = ''
        return self._content

    def _copy_to_component(self, parent_component: Type[ComponentBase], name: str) -> T:
        self.set_filename(name)
        self = copy.copy(self)
        self.path = parent_component.path.joinpath(self.filename)
        if self.required and not self.path.is_file():
            raise ComponentError(
                f"Cannot load {self.__class__.__name__} from '{self.path}': not a file"
            )
        return self

    def set_filename(self, name: str) -> None:
        self.filename = self.filename or name

    def copy_to_component(self, component: Type[ComponentBase], name: str) -> None:
        self = self._copy_to_component(component, name)
        setattr(component, name, self)
        component.files.append(self)

    def init(self, parent_component: Type[ComponentBase]) -> None:
        if self.content_fn is None:
            return
        path = parent_component.path.joinpath(self.filename)
        path.write_text(self.content_fn(parent_component))


class Lambda(ComponentBase):
    abstract = True

    def load_config(self):
        self.config = NamedYamlable.from_yaml(self.definition.content)
        self.description = self.config.get('description', '')
        self.python_requirements = self.config.pop('python_requirements', [])
        if not hasattr(self.config, 'module'):
            self.config.module = f'{self.plural_name}/{self.name}'
        if not hasattr(self.config, 'handler'):
            self.config.handler = f'{self.component_type}.handler'

    # TODO: not sure, but I think we should include the default
    # lambda files and have methods on the class to define the
    # content, which can be overriden as approprite by subclasses
    @property
    def definition(self):
        raise NotImplementedError("Must define a file named 'definition'")


class StepFunction(ComponentBase):
    abstract = True

    def load_config(self):
        self.config = NamedYamlable.from_yaml(self.definition.content)
        try:
            self.description = self.config.definition.Comment
        except AttributeError:
            pass

    # TODO: same as the note on lambdas above, may make more sense
    # to have default files declared here and methods on the class
    # that can be overriden to provide default content
    @property
    def definition(self):
        raise NotImplementedError("Must define a file named 'definition'")
