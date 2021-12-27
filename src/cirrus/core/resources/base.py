import logging
import click
import sys

from pathlib import Path
from itertools import chain

from cirrus.core.utils.yaml import NamedYamlable
from cirrus.core.utils import misc
from cirrus.core.group_meta import GroupMeta


logger = logging.getLogger(__name__)


class CFObjectMeta(GroupMeta):
    cf_types = {}

    def __new__(cls, name, bases, attrs, **kwargs):
        if 'user_extendable' not in attrs:
            attrs['user_extendable'] = True

        abstract = attrs.get('abstract', False)

        top_level_key = attrs.get('top_level_key', None)
        if not (
            top_level_key
            or abstract
            or [base for base in bases if hasattr(base, 'top_level_key')]
        ):
            raise NotImplementedError(f"Must define the 'top_level_key' attr on '{name}'")

        self = super().__new__(cls, name, bases, attrs, **kwargs)

        if top_level_key:
            if top_level_key in cls.cf_types:
                raise ValueError(
                    f"Cannot declare class '{name}' with top_level_key '{top_level_key}': already in use",
                )
            cls.cf_types[attrs['top_level_key']] = self

        return self

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type = self.__name__.lower()

    def from_file(self, path: Path):
        cf = NamedYamlable.from_file(path)
        for top_level_key, cf_objects in cf.items():
            cls = self.cf_types.get(top_level_key, None)
            for name, definition in cf_objects.items():
                if cls is None:
                    logger.warning(
                        "Skipping item '%s': Unknown cloudformation object type '%s'",
                        name,
                        top_level_key,
                    )
                    continue
                yield cls(name, definition, path)

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

        def cf_finder():
            yield from self._find(search_dirs=self.get_search_dirs())
            yield from chain.from_iterable(filter(bool, map(
                lambda r: r.batch_resources if r.batch_enabled else None,
                self.parent.tasks.values(),
            )))

        for cf_object in cf_finder():
            if cf_object.name in self._elements:
                logger.warning(
                    "Duplicate %s declaration '%s', overriding",
                    self.type,
                    cf_object.name,
                )
            self._elements[cf_object.name] = cf_object

    def add_show_command(self, show_cmd):
        @show_cmd.command(
            name=self.group_name,
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
                logger.error("Cannot show %s: none found", self.group_name)
            else:
                logger.error("Cannot show %s: no matches for '%s'", self.group_name, name)


class BaseCFObject(metaclass=CFObjectMeta):
    abstract = True

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
