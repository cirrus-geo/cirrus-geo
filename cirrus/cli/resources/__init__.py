import logging
import click

from pathlib import Path

from cirrus.cli.utils.yaml import NamedYamlable
from cirrus.cli.utils import misc


logger = logging.getLogger(__name__)


CORE_DIR = Path(__file__).parent.joinpath('config')


class Resource():
    name = 'resource'
    top_level_key = 'Resources'
    user_extendable = True

    def __init__(self, name, definition, path: Path=None) -> None:
        self.name = name
        self.definition = definition
        self.type = definition.get('Type', '')
        self.path = path
        self.is_core_component = self.path.parent.samefile(CORE_DIR) if self.path else False

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

        search_dirs = [CORE_DIR] + search_dirs

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
        return '{}{} ({})'.format(
            self.name,
            f' [{self.type}]' if self.type else '',
            self.display_source,
        )

    def list_display(self):
        click.secho(self.display_name, fg='blue')

    def detail_display(self):
        self.list_display()
        click.echo(self.definition.to_yaml())

    @classmethod
    def add_show_command(cls, collection, show_cmd):
        @show_cmd.command(
            name=collection.name,
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


class TaskResource(Resource):
    def __init__(self, parent_task, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.parent_task = parent_task

    @property
    def display_source(self):
        built_in = 'built-in ' if self.parent_task.is_core_component else ''
        return f'from {built_in}task {self.parent_task.name}'
