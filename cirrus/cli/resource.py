import sys
import copy
import click

from typing import Type, TypeVar
from abc import ABCMeta
from pathlib import Path
from rich.markdown import Markdown

from cirrus.cli.config import Config
from cirrus.cli.exceptions import CirrusError, ResourceLoadError
from cirrus.cli.project import project
from cirrus.cli.console import console


class ResourceMeta(ABCMeta):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.resource_type=self.__name__.lower()
        self.plural_name = f'{self.resource_type}s'
        self.default_user_dir_name = self.plural_name
        self.core_dir = Path(sys.modules[self.__module__].__file__,).parent.joinpath('config')

        self.cli_group_name = self.plural_name
        self.cli_help = f'Commands for managing {self.resource_type} resources'
        self.cli = build_resouce_cli(self)

    @property
    def default_user_dir(self):
        return project.path.joinpath(self.default_user_dir_name)


def build_resouce_cli(cls: Type[ResourceMeta]):
    @click.group(
        name=cls.cli_group_name,
        help=cls.cli_help,
    )
    def cli():
        pass

    @cli.command()
    def list():
        for resource in cls.find():
            click.echo('{}{}'.format(
                resource.name,
                ' (built-in)' if resource.is_core_resource else '',
            ))

    @cli.command()
    @click.argument(
        'name',
        metavar=f'{cls.resource_type}-name',
    )
    def new(name):
        pass
        #cls.new(name)

    if hasattr(cls, 'readme'):
        @cli.command()
        @click.argument(
            'name',
            metavar=f'{cls.resource_type}-name',
        )
        def readme(name):
            resource = cls.find_first(name)
            if not resource:
                click.secho(
                    f"Unable to find {cls.resource_type} with name '{name}'.",
                    err=True,
                    fg='red',
                )
                return

            if resource.readme.content is None:
                click.secho(
                    f"{cls.resource_type.capitalize()} '{name}' has no README.",
                    err=True,
                    fg='red',
                )
                return

            console.print(Markdown(resource.readme.content))

    return cli


T = TypeVar('T', bound='ResourceBase')
class ResourceBase(metaclass=ResourceMeta):
    def __init__(self, path: Path) -> None:
        self.path = path

        if not self.path.is_dir():
            raise ResourceLoadError(
                f"Cannot load {self.__class__.__name__} from '{self.path}': not a directory"
            )

        self.name = path.name

        self.is_core_resource = self.path.parent.samefile(self.__class__.core_dir)

        self.files = []
        for attr, val in self.__class__.__dict__.items():
            if hasattr(val, 'copy_to_resource'):
                val.copy_to_resource(self, attr)

    @classmethod
    def from_dir(cls, d: Path, name: str=None) -> Type[T]:
        for resource_dir in d.resolve().iterdir():
            if name and resource_dir.name != name:
                continue
            try:
                yield cls(resource_dir)
            except ResourceLoadError:
                # TODO: logging of skipped dirs
                continue

    @classmethod
    def find(cls, name: str=None) -> Type[T]:
        # search user dir first, as we prefer a user
        # implementation if a resource name is specified
        search_dirs = []

        try:
            search_dirs.append(cls.default_user_dir)
        except CirrusError:
            pass

        search_dirs.append(cls.core_dir)

        for _dir in search_dirs:
            yield from cls.from_dir(_dir, name=name)

    @classmethod
    def find_first(cls, name: str) -> Type[T]:
        try:
            return next(cls.find(name=name))
        except StopIteration:
            return None



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
