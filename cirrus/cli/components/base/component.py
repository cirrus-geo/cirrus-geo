import sys
import logging
import click

from typing import Type, TypeVar
from abc import ABCMeta
from pathlib import Path

from cirrus.cli import commands
from cirrus.cli.exceptions import ComponentError
from cirrus.cli.project import project


logger = logging.getLogger(__name__)


T = TypeVar('T', bound='Component')
class ComponentMeta(ABCMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        if not 'user_extendable' in attrs:
            attrs['user_extendable'] = True
        return super().__new__(cls, name, bases, attrs, **kwargs)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # TODO: better name attr, clean up the others
        self.component_type = self.__name__.lower()
        self.name = self.__name__.lower()
        self.user_dir_name = f'{self.name}s'
        self.core_dir = Path(sys.modules[self.__module__].__file__,).parent.joinpath('config')

    @property
    def user_dir(self):
        if self.user_extendable:
            try:
                return project.path_safe.joinpath(self.user_dir_name)
            except AttributeError:
                pass
        return None


class Component(metaclass=ComponentMeta):
    def __init__(self, path: Path, load: bool=True) -> None:
        self.path = path
        self.name = path.name
        self.files = {}
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
        path = cls.user_dir.joinpath(name)
        new = cls(path, load=False)
        try:
            new._create()
        except ComponentError:
            raise
        except Exception as e:
            # want to clean up anything
            # we created if we failed
            import shutil
            try:
                shutil.rmtree(new.path)
            except FileNotFoundError:
                pass
            raise
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
        search_dirs = [cls.core_dir]

        user_dir = cls.user_dir
        if user_dir is not None:
            search_dirs.append(user_dir)

        for _dir in search_dirs:
            yield from cls.from_dir(_dir, name=name)

    def list_display(self):
        click.echo('{}{}'.format(
            click.style(
                f'{self.display_name}:',
                fg='blue',
            ),
            f' {self.description}'
            if self.description else '',
        ))

    def detail_display(self):
        click.secho(self.display_name, fg='blue')
        if self.description:
            click.echo(self.description)
        click.echo("\nFiles:")
        for name, f in self.files.items():
            click.echo("  {}: {}".format(
                click.style(name, fg='yellow'),
                f.name,
            ))

    @classmethod
    def add_create_command(cls):
        if not cls.user_extendable:
            return

        @commands.create.command(
            name=cls.component_type
        )
        @click.argument(
            'name',
            metavar='name',
        )
        def _create(name):
            import sys
            from cirrus.cli.exceptions import ComponentError

            try:
                cls.create(name)
            except ComponentError as e:
                logger.error(e)
                sys.exit(1)
            else:
                # TODO: logging level for "success" on par with warning?
                click.secho(
                    f'{cls.component_type} {name} created',
                    err=True,
                    fg='green',
                )

    @classmethod
    def add_show_command(cls, collection):
        @commands.show.command(
            name=collection.name,
        )
        @click.argument(
            'name',
            metavar='name',
            required=False,
        )
        @click.argument(
            'filename',
            metavar='filename',
            required=False,
        )
        def _show(name=None, filename=None):
            if name is None:
                for element in collection.values():
                    element.list_display()
                return

            try:
                element = collection[name]
            except KeyError:
                logger.error("Cannot show: unknown %s '%s'", collection.element_class.name, name)

            if filename is None:
                element.detail_display()
                return

            try:
                element.files[filename].show()
            except KeyError:
                logger.error("Cannot show: unknown file '%s'", filename)