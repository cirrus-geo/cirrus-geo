import sys
import copy
import click

from typing import Type, TypeVar, Callable
from abc import ABCMeta
from pathlib import Path
from rich.markdown import Markdown

from cirrus.cli.exceptions import CirrusError, ResourceError
from cirrus.cli.project import project
from cirrus.cli.utils.console import console
#from cirrus.cli.utils.markdown import Markdown
from cirrus.cli.utils.yaml import NamedYamlable


class ResourceMeta(ABCMeta):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.resource_type=self.__name__.lower()
        self.plural_name = f'{self.resource_type}s'
        self.default_user_dir_name = self.plural_name
        self.core_dir = Path(sys.modules[self.__module__].__file__,).parent.joinpath('config')

        if self.enable_cli:
            self.cli_group_name = self.plural_name
            self.cli_help = f'Commands for managing {self.resource_type} resources'
            self._build_cli()

    @property
    def default_user_dir(self):
        if self.user_extendable:
            try:
                return project.path_safe.joinpath(self.default_user_dir_name)
            except AttributeError:
                pass
        return None

    def _build_cli(self) -> None:
        @click.group(
            name=self.cli_group_name,
            help=self.cli_help,
        )
        def cli():
            pass

        self.cli = cli
        self.build_cli()

    def build_cli(self):
        @self.cli.command()
        def list():
            for resource in self.find():
                click.echo('{}{}{}'.format(
                    resource.name,
                    ' (built-in)' if resource.is_core_resource else '',
                    f': {resource.description}' if resource.description else '',
                ))

        @self.cli.command()
        @click.argument(
            'name',
            metavar=f'{self.resource_type}-name',
        )
        def new(name):
            # TODO: extract project path check into requires_project decorator
            if project._path is None:
                # TODO: custom exception handler for click exceptions that supports colors
                click.secho('Cannot create resource: not in a cirrus project', err=True, fg='red')
                sys.exit(1)
            try:
                self.create(name)
            except ResourceError as e:
                click.secho(e, err=True, fg='red')
                sys.exit(1)
            else:
                click.secho(f'{self.resource_type} {name} created', err=True, fg='green')

        if hasattr(self, 'readme'):
            @self.cli.command()
            @click.argument(
                'name',
                metavar=f'{self.resource_type}-name',
            )
            def readme(name):
                resource = self.find_first(name)
                if not resource:
                    click.secho(
                        f"Unable to find {self.resource_type} with name '{name}'.",
                        err=True,
                        fg='red',
                    )
                    return

                if resource.readme.content is None:
                    click.secho(
                        f"{self.resource_type.capitalize()} '{name}' has no README.",
                        err=True,
                        fg='red',
                    )
                    return

                console.print(Markdown(resource.readme.content))


T = TypeVar('T', bound='ResourceBase')
class ResourceBase(metaclass=ResourceMeta):
    enable_cli = True
    user_extendable = True

    def __init__(self, path: Path, load: bool=True) -> None:
        self.path = path
        self.name = path.name
        self.files = []
        self.config = None
        self.description = ''
        self.is_core_resource = self.path.parent.samefile(self.__class__.core_dir)
        self._loaded = False
        if load:
            self._load()

    def _load(self, init_resources=False):
        if not self.path.is_dir():
            raise ResourceError(
                f"Cannot load {self.resource_type} from '{self.path}': not a directory."
            )

        for attr, val in self.__class__.__dict__.items():
            if hasattr(val, 'copy_to_resource'):
                if init_resources:
                    val.init()
                val.copy_to_resource(self, attr)

        if hasattr(self, 'definition'):
            self.config = NamedYamlable.from_yaml(self.definition.content)
            self.process_config()
        self._loaded = True

    def process_config(self):
        if not hasattr(self.config, 'module'):
            self.config.module = f'{self.plural_name}/{self.name}'
        if not hasattr(self.config, 'handler'):
            self.config.handler = f'{self.resource_type}.handler'
        if hasattr(self.config, 'description'):
            self.description = self.config.description

    def _create(self):
        if self._loaded:
            raise ResourceError(f'Cannot create a loaded {self.__class__.__name__}.')
        try:
            self.path.mkdir()
        except FileExistsError as e:
            raise ResourceError(
                f"Cannot create {self.__class__.__name__} at '{self.path}': already exists."
            ) from e
        self._load(init_resources=True)

    @classmethod
    def create(cls, name: str) -> Type[T]:
        if not cls.user_extendable:
            raise ResourceError(
                f"Resource {self.resource_type} does not support creation"
            )
        path = cls.default_user_dir.joinpath(name)
        new = cls(path, load=False)
        new._create()
        return new

    @classmethod
    def from_dir(cls, d: Path, name: str=None) -> Type[T]:
        for resource_dir in d.resolve().iterdir():
            if name and resource_dir.name != name:
                continue
            try:
                yield cls(resource_dir)
            except ResourceError:
                # TODO: logging of skipped dirs
                continue

    @classmethod
    def find(cls, name: str=None) -> Type[T]:
        # search user dir first, as we prefer a user
        # implementation if a resource name is specified
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



T = TypeVar('T', bound='ResourceFile')
class ResourceFile:
    def __init__(
        self,
        filename:
        str=None,
        optional: bool=False,
        content_fn: Callable[[Type[ResourceBase]], str]=None,
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
                    raise ResourceError(
                            f"{self.__class__.__name__} at '{self.path}': unable to open for read"
                    ) from e
                else:
                    # log something about defaulting content to None
                    self._content = ''
        return self._content

    def _copy_to_resource(self, parent_resource: Type[ResourceBase], name: str) -> T:
        self.set_filename(name)
        self = copy.copy(self)
        self.path = parent_resource.path.joinpath(self.filename)
        if self.required and not self.path.is_file():
            raise ResourceError(
                f"Cannot load {self.__class__.__name__} from '{self.path}': not a file"
            )
        return self

    def set_filename(self, name: str) -> None:
        self.filename = self.filename or name

    def copy_to_resource(self, resource: Type[ResourceBase], name: str) -> None:
        self = self._copy_to_resource(resource, name)
        setattr(resource, name, self)
        resource.files.append(self)

    def init(self, parent_resource: Type[ResourceBase]) -> None:
        if self.content_fn is None:
            return
        path = parent_resource.path.joinpath(self.filename)
        path.write_text(self.content_fn(parent_resource))
