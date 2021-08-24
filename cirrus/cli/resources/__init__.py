import logging
import click

from pathlib import Path

from cirrus.cli import commands
from cirrus.cli.project import project
from cirrus.cli.collection import Collection
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


CORE_DIR = Path(__file__).parent.joinpath('config')


class Resource():
    name = 'resource'
    top_level_key = 'Resources'

    def __init__(self, name, definition, file: Path=None) -> None:
        self.name = name
        self.definition = definition
        self.type = definition.get('Type', '')
        self.file = file
        self.is_core_component = self.file.parent.samefile(CORE_DIR) if self.file else False

    @classmethod
    def from_file(cls, f: Path):
        resources = NamedYamlable.from_file(f)
        try:
            resources = resources[cls.top_level_key]
        except KeyError:
            pass

        for name, definition in resources.items():
            yield cls(name, definition, f)

    @classmethod
    def find(cls):
        search_dirs = (
            Path(__file__).parent.joinpath('config'),
            project.path.joinpath('resources'),
        )
        for d in search_dirs:
            for yml in d.glob('*.yml'):
                yield from cls.from_file(yml)

    @property
    def display_name(self):
        return '{}{}{}'.format(
            self.name,
            f' [{self.type}]' if self.type else '',
            ' (built-in)' if self.is_core_component else '',
        )

    def list_display(self):
        click.secho(self.display_name, fg='blue')

    def detail_display(self):
        self.list_display()
        click.echo(self.definition.to_yaml())

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
        def _show(name=''):
            name = name.lower()
            elements = []
            for element in collection.values():
                if not name or name in element.name.lower():
                    elements.append(element)

            if len(elements) > 1:
                for element in elements:
                    element.list_display()
            elif len(elements) == 1:
                elements[0].detail_display()
            else:
                logger.error("Cannot show %s: no matches for '%s'", collection.element_class.name, name)


resources = Collection(
    'resources',
    Resource,
)
