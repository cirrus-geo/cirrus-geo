import logging
import click
import sys

from pathlib import Path
from itertools import chain

from cirrus.cli.utils.yaml import NamedYamlable
from cirrus.cli.utils import misc
from cirrus.cli.collection_meta import CollectionMeta


logger = logging.getLogger(__name__)


class ResourceMeta(CollectionMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        if 'user_extendable' not in attrs:
            attrs['user_extendable'] = True

        if 'top_level_key' not in attrs and not [base for base in bases if hasattr(base, 'top_level_key')]:
            raise NotImplementedError(f"Must define the 'top_level_key' attr on '{name}'")

        return super().__new__(cls, name, bases, attrs, **kwargs)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type = self.__name__.lower()
        self.core_dir = Path(sys.modules[self.__module__].__file__,).parent.joinpath('config')

    def from_file(self, path: Path):
        resources = NamedYamlable.from_file(path)
        try:
            resources = resources[self.top_level_key]
        except KeyError:
            pass

        for name, definition in resources.items():
            yield self(name, definition, path)

    def _find(self, search_dirs=None):
        if search_dirs is None:
            search_dirs = []

        if self.core_dir.is_dir():
            search_dirs = [self.core_dir] + search_dirs

        for d in search_dirs:
            for yml in sorted(d.glob('*.yml')):
                yield from self.from_file(yml)

    def find(self):
        self._elements = {}

        def resource_finder():
            yield from self._find(search_dirs=self.get_search_dirs())
            yield from chain.from_iterable(filter(bool, map(
                lambda r: r.batch_resources if r.batch_enabled else None,
                self.parent.tasks.values(),
            )))

        for resource in resource_finder():
            if resource.name in self._elements:
                logger.warning(
                    "Duplicate %s declaration '%s', overriding",
                    self.type,
                    resource.name,
                )
            self._elements[resource.name] = resource

    def add_show_command(self, show_cmd):
        @show_cmd.command(
            name=self.collection_name,
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
            for element in self.values():
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
                logger.error("Cannot show %s: none found", self.collection_name)
            else:
                logger.error("Cannot show %s: no matches for '%s'", self.collection_name, name)


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
