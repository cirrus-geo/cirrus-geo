import copy

from typing import Type, TypeVar
from abc import ABC
from pathlib import Path

from cirrus.config import Config
from cirrus.exceptions import ResourceLoadError

T = TypeVar('T', bound='ResourceBase')
class ResourceBase(ABC):
    def __init__(self, path: Path) -> None:
        self.path = path

        if not self.path.is_dir():
            raise ResourceLoadError(
                f"Cannot load {self.__class__.__name__} from '{self.path}': not a directory"
            )

        self.name = path.name

        self.files = []
        for attr, val in self.__class__.__dict__.items():
            if hasattr(val, 'copy_to_resource'):
                val.copy_to_resource(self, attr)

    @classmethod
    def from_dir(cls, d: Path, name: str=None) -> Type[T]:
        for resource_dir in d.resolve().iterdir():
            if name and resource_dir != name:
                continue
            try:
                yield cls(resource_dir)
            except ResourceLoadError:
                # TODO: logging of skipped dirs
                continue

    @classmethod
    def find(cls, config: Config, name: str=None) -> Type[T]:
        plural_name = cls.plural_name if hasattr(cls.plural_name) else f'{cls.__name__.lower()}s'

        # search user dirs first, as we want to prefer user
        # implementations of a given name
        search_dirs = getattr(Config, plural_name).sources
        try:
            search_dirs.append(cls.default_search_dir)
        except AttributeError:
            pass

        for _dir in search_dirs:
            yield from cls.from_dir(_dir, name=name)


T = TypeVar('T', bound='ResourceFile')
class ResourceFile:
    def __init__(self, filename: str=None, optional: bool=False) -> None:
        self.filename = filename
        self.required = not optional

    def _copy(self, parent_resource: Type[ResourceBase], name: str) -> T:
        self.set_filename(name)
        self = copy.copy(self)
        self.path = parent_resource.path.joinpath(self.filename)
        try:
            with self.path.open() as f:
                self.content = f.read()
        except FileNotFoundError as e:
            if self.required:
                raise ResourceLoadError(
                        f"Cannot load {self.__class__.__name__} from '{self.path}': unable to open for read"
                ) from e
            else:
                # log something about defaulting content to None
                self.content = None
        return self

    def set_filename(self, name: str) -> None:
        self.filename = self.filename or name

    def copy_to_resource(self, resource: Type[ResourceBase], name: str) -> None:
        self = self._copy(resource, name)
        setattr(resource, name, self)
        resource.files.append(self)
