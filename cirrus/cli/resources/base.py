import logging
import click
import sys

from abc import ABCMeta
from pathlib import Path

from cirrus.cli.utils.yaml import NamedYamlable
from cirrus.cli.utils import misc


logger = logging.getLogger(__name__)


class ResourceMeta(ABCMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        if not 'user_extendable' in attrs:
            attrs['user_extendable'] = True

        if not 'top_level_key' in attrs and not [base for base in bases if hasattr(base, 'top_level_key')]:
            raise NotImplementedError(f"Must define the 'top_level_key' attr on '{name}'")

        return super().__new__(cls, name, bases, attrs, **kwargs)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type = self.__name__.lower()
        self.core_dir = Path(sys.modules[self.__module__].__file__,).parent.joinpath('config')

    def register_collection(self, collection):
        self.collection = collection


class BaseResource(metaclass=ResourceMeta):
    top_level_key = 'Resources'

    def __init__(self, name, definition, path: Path=None) -> None:
        self.name = name
        self.definition = definition
        self.path = path
        self.is_core_component = (
            self.path.parent.samefile(self.core_dir)
            if self.path and self.core_dir.is_dir() else False
        )

    @classmethod
    def from_file(cls, path: Path):
        resources = NamedYamlable.from_file(path)
        try:
            resources = resources[cls.top_level_key]
        except KeyError:
            pass

        for name, definition in resources.items():
            yield cls(name, definition, path)

    @classmethod
    def find(cls, search_dirs=None):
        if search_dirs is None:
            search_dirs = []

        if cls.core_dir.is_dir():
            search_dirs = [cls.core_dir] + search_dirs

        for d in search_dirs:
            for yml in d.glob('*.yml'):
                yield from cls.from_file(yml)

    @property
    def display_source(self):
        if self.is_core_component:
            return 'built-in'
        return misc.relative_to_cwd(self.path)

    @property
    def display_name(self):
        return '{} ({})'.format(
            self.name,
            self.display_source,
        )

    def list_display(self):
        click.secho(self.display_name, fg='blue')

    def detail_display(self):
        self.list_display()
        click.echo(self.definition.to_yaml())

    @classmethod
    def add_show_command(cls, show_cmd):
        @show_cmd.command(
            name=cls.collection.name,
        )
        @click.argument(
            'name',
            metavar='name',
            required=False,
            default='',
            callback=lambda ctx, param, val: val.lower(),
        )
        def _show(name):
            elements = []
            for element in cls.collection.values():
                if name == element.name.lower():
                    elements = [element]
                    break
                if not name or name in element.name.lower():
                    elements.append(element)

            if name and len(elements) == 1:
                elements[0].detail_display()
            elif elements:
                for element in elements:
                    element.list_display()
            elif not name:
                logger.error("Cannot show %s: none found", cls.collection.name)
            else:
                logger.error("Cannot show %s: no matches for '%s'", cls.collection.name, name)
