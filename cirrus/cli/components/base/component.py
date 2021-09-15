import sys
import logging
import click

from typing import Type, TypeVar
from abc import ABCMeta
from pathlib import Path

from ..files import ComponentFile
from cirrus.cli.exceptions import ComponentError


logger = logging.getLogger(__name__)


T = TypeVar('T', bound='Component')
class ComponentMeta(ABCMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        files = attrs.get('files', {})

        # copy file attrs to files
        for attr_name, attr in attrs.items():
            if isinstance(attr, ComponentFile):
                files[attr_name] = attr

        # copy parent class files to child,
        # if not overridden on child
        for base in bases:
            if hasattr(base, 'files'):
                for fname, f in base.files.items():
                    if fname not in attrs:
                        attrs[fname] = f
                        files[fname] = f

        attrs['files'] = files

        if not 'user_extendable' in attrs:
            attrs['user_extendable'] = True

        return super().__new__(cls, name, bases, attrs, **kwargs)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # TODO: better name attr, clean up the others
        self.component_type = self.__name__.lower()
        self.name = self.__name__.lower()
        self.core_dir = Path(sys.modules[self.__module__].__file__,).parent.joinpath('config')


class Component(metaclass=ComponentMeta):
    def __init__(self, path: Path, load: bool=True) -> None:
        self.path = path
        self.name = path.name
        self.config = None
        self.description = ''
        self.is_core_component = self.path.parent.samefile(self.__class__.core_dir)

        self.files = {}
        for fname, f in self.__class__.files.items():
            f.copy_to_component(self, fname)

        self._loaded = False
        if load:
            self._load()

    @property
    def display_name(self):
        return '{}{}'.format(
            self.name,
            ' (built-in)' if self.is_core_component else '',
        )

    def _load(self, init_files=False):
        if not self.path.is_dir():
            raise ComponentError(
                f"Cannot load {self.component_type} from '{self.path}': not a directory."
            )

        # TODO: this whole load/init thing
        # needs some heavy cleanup
        for f in self.files.values():
            if init_files:
                f.init(self)
            f.validate()

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
        self._load(init_files=True)

    @classmethod
    def create(cls, name: str, outdir: Path) -> Type[T]:
        if not cls.user_extendable:
            raise ComponentError(
                f"Component {self.component_type} does not support creation"
            )
        path = outdir.joinpath(name)
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
                logger.warning(
                    f"Directory does not appear to be a {cls.component_type}, skipping: '{component_dir}'",
                )
                continue

    @classmethod
    def find(cls, name: str=None, search_dirs: list=None) -> Type[T]:
        if search_dirs is None:
            search_dirs = []

        search_dirs = [cls.core_dir] + search_dirs

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
    def add_create_command(cls, collection, create_cmd):
        if not cls.user_extendable:
            return

        @create_cmd.command(
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
                collection.create(name)
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
    def add_show_command(cls, collection, show_cmd):
        @show_cmd.command(
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
