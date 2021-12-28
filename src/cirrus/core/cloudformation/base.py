import logging
import click

from pathlib import Path
from itertools import chain

from cirrus.core.utils.yaml import NamedYamlable
from cirrus.core.utils import misc
from cirrus.core.group_meta import GroupMeta


logger = logging.getLogger(__name__)


class CFObjectMeta(GroupMeta):
    cf_types = {}
    skipped_cf_types = [
        'AWSTemplateFormatVersion',
        'Description',
    ]

    # we use _cf_objects as an extension of the GroupMeta
    # _elements property, to index all cf objects by top
    # level key
    _cf_objects = None

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

    @property
    def cf_objects(self):
        if self._cf_objects is None:
            self.find()
        return self._cf_objects

    def reset_elements(self, *args, **kwargs):
        super().reset_elements(*args, **kwargs)
        self._cf_objects = None

    def from_file(self, path: Path):
        cf = NamedYamlable.from_file(path)
        for top_level_key, cf_objects in cf.items():
            if top_level_key in self.skipped_cf_types:
                continue
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
        self._cf_objects = {tlk: list() for tlk in self.cf_types.keys()}

        def cf_finder():
            # order here matters
            # later takes precedence
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
            self._cf_objects[cf_object.top_level_key].append(cf_object)

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
        @click.option(
            '-t',
            '--type',
            'filter_types',
            multiple=True,
            type=click.Choice(
                self.cf_types.keys(),
                case_sensitive=False,
            ),
        )
        def _show(name, filter_types=None):
            # filter cf object lists by selected filter types
            object_items = [
                (tlk, cfos)
                for tlk, cfos in self.cf_objects.items()
                if not filter_types or tlk in filter_types
            ]

            # iterate through the different cf types
            # to collect all matches based on `name`
            elements = {}
            found_count = 0
            for top_level_key, cf_objects in object_items:
                # look through the cf type group for matches
                els = []
                for cf_object in cf_objects:
                    if name == cf_object.name.lower():
                        # an exact match will stop matching and
                        # throw away any other matches
                        els = [cf_object]
                        break
                    if not name or name in cf_object.name.lower():
                        els.append(cf_object)

                # if matches, store them in the result dict
                if els:
                    elements[top_level_key] = els
                    found_count += len(els)

            if name and found_count == 1:
                # if only one matched, we should use detail display
                list(elements.values())[0][0].detail_display()
            elif elements:
                # otherwise we list them, each type with a header
                first_line = True
                for tlk, els in elements.items():
                    if first_line:
                        first_line = False
                    else:
                        click.echo('')
                    click.secho(tlk, fg='green')
                    for element in els:
                        element.list_display()
            elif not name:
                logger.error(
                    'Cannot show %s: none found',
                    self.group_display_name,
                )
            else:
                logger.error(
                    "Cannot show %s: no matches for '%s'",
                    self.group_display_name,
                    name,
                )


class BaseCFObject(metaclass=CFObjectMeta):
    '''Base class for all cloudformation types.'''
    abstract = True

    def __init__(self, name, definition,
                 path: Path=None, parent_task=None) -> None:
        self.name = name
        self.definition = definition
        self.path = path
        self.resource_type = definition.get('Type', None)
        self.parent_task = parent_task
        # TODO: fix is_core_component logic
        self.is_core_component = (
            self.path.parent.samefile(self.core_dir)
            if self.path and self.core_dir.is_dir() else False
        )

    @property
    def display_source(self):
        if self.parent_task:
            built_in = 'built-in ' if self.parent_task.is_core_component else ''
            return f'from {built_in}task {self.parent_task.name}'
        elif self.is_core_component:
            return 'built-in'
        return misc.relative_to_cwd(self.path)

    def make_display_name(self, show_type=True):
        show_type = show_type and self.resource_type
        return '{}{} ({})'.format(
            self.name,
            f' [{self.resource_type}]' if show_type else '',
            self.display_source,
        )

    @property
    def display_name(self):
        return self.make_display_name()

    def list_display(self, show_type=True):
        click.secho(self.make_display_name(show_type=show_type), fg='blue')

    def detail_display(self):
        self.list_display(show_type=False)
        click.echo(self.definition.to_yaml())


class CloudFormation(metaclass=CFObjectMeta):
    '''Used as the group added to Groups.
    Tracks all cloudformation objects of other types.
    '''
    abstract = True
    group_name = 'cloudformation'
    group_display_name = 'CloudFormation'
