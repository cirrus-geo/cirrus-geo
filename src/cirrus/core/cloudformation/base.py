import logging
import textwrap
from itertools import chain
from pathlib import Path

import click

from cirrus.core.exceptions import CloudFormationError, CloudFormationSkipped
from cirrus.core.group_meta import GroupMeta
from cirrus.core.utils import misc
from cirrus.core.utils.yaml import NamedYamlable

logger = logging.getLogger(__name__)

BUILT_IN = "built-in"


class CFObjectMeta(GroupMeta):
    # All concrete subclasses are added to this dict
    # using their `top_level_key` as the dict key.
    # We use this class as a lookup when instantiating
    # an object for each cloudformation object in a
    # cf file in `from_file`, and anywhere else we need
    # a reference to all the top_level_keys/cf classes.
    cf_types = {}

    # Skipped types are those we don't care to copy
    # over into the output cf template. Generally,
    # these are things that cannot be unique across
    # templates, i.e., only one value in the output
    # template is acceptable.
    skipped_cf_types = [
        "AWSTemplateFormatVersion",
        "Description",
    ]

    ####
    # We use the `elements` property a bit different here than
    # on the `GroupMeta` base class. We need to maintain a list of
    # cf objects per type, rather than one list across all types.
    # As a result, we end up with a heirarchial dict like:
    #
    #     elements[cf_top_level_key][cf_object_name]: cf_object
    #
    # See `find` for where we initialize `elements`.
    #
    # We override the following `GroupMeta` methods as a consequence.
    def __iter__(self):
        yield from (
            cf_obj for cf_type in self.elements.values() for cf_obj in cf_type.values()
        )

    def __len__(self):
        return sum(len(d) for d in self.elements.values())

    def __setitem__(self, key, val):
        self.elements[val.top_level_key][key] = val

    ####

    def __new__(cls, name, bases, attrs, **kwargs):
        if "user_extendable" not in attrs:
            attrs["user_extendable"] = False

        abstract = attrs.get("abstract", False)

        # top_level_key is like `Resources` or `Outputs`
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-anatomy.html
        top_level_key = attrs.get("top_level_key", None)
        if not (
            top_level_key
            or abstract
            or [base for base in bases if hasattr(base, "top_level_key")]
        ):
            raise NotImplementedError(
                f"Must define the 'top_level_key' attr on '{name}'"
            )

        self = super().__new__(cls, name, bases, attrs, **kwargs)

        if top_level_key:
            if top_level_key in cls.cf_types:
                raise ValueError(
                    f"Cannot declare class '{name}' with top_level_key '{top_level_key}': already in use",
                )
            cls.cf_types[attrs["top_level_key"]] = self

        return self

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type = self.__name__.lower()

    def resolve_cls(self, top_level_key):
        if top_level_key in self.skipped_cf_types:
            raise CloudFormationSkipped()

        try:
            return self.cf_types[top_level_key]
        except KeyError:
            raise CloudFormationError(
                f"Unknown cloudformation type '{top_level_key}'",
            )

    def create_cf_objects(
        self,
        path,
        top_level_key,
        objects,
        source: str = None,
        parent_component=None,
    ):
        if top_level_key in self.skipped_cf_types:
            return

        project = parent_component.project if parent_component else self.project
        for name, definition in objects.items():
            try:
                yield CFObject(
                    top_level_key,
                    name,
                    definition,
                    path,
                    source=source,
                    parent_component=parent_component,
                    project=project,
                )
            except CloudFormationSkipped:
                pass
            except CloudFormationError as e:
                logger.warning(
                    "Skipping item '%s': %s",
                    name,
                    e,
                )

    def from_file(self, path: Path, source: str = None):
        # only process files
        if not path.is_file():
            return

        # ignore files starting with '.'
        if path.name.startswith("."):
            return

        # parse a yml cf file
        cf = NamedYamlable.from_file(path)

        # iterate through and instantiate all cf objects
        for top_level_key, cf_objects in cf.items():
            yield from self.create_cf_objects(
                path,
                top_level_key,
                cf_objects,
                source=source,
            )

    def _find(self):
        def search_dir(path, source=None):
            for yml in sorted(path.glob("*.yml")):
                try:
                    yield from self.from_file(yml, source=source)
                except ValueError:
                    logger.warning(
                        "Unable to load cloudformation file '%s': "
                        "appears malformatted",
                        misc.relative_to_cwd(yml),
                    )

        for plugin_name, plugin_dir in self.plugins.items():
            yield from search_dir(plugin_dir, source=plugin_name)

        if self.user_dir and self.user_dir.is_dir():
            yield from search_dir(self.user_dir)

    def find(self):
        self._elements = {tlk: {} for tlk in self.cf_types.keys()}

        def cf_finder():
            # order here matters, later takes precedence
            # so we prefer objects defined on tasks
            yield from self._find()
            yield from chain.from_iterable(
                filter(
                    bool,
                    map(
                        lambda task: task.batch_cloudformation
                        if task.batch_enabled
                        else None,
                        self.parent.tasks,
                    ),
                )
            )

        # cf_finder yields cf object instances, so here
        # we iterate through all cf objects it finds
        for cf_object in cf_finder():
            if cf_object.name in self[cf_object.top_level_key]:
                logger.warning(
                    "Duplicate %s declaration '%s', overriding",
                    cf_object.top_level_key,
                    cf_object.name,
                )
            self[cf_object.name] = cf_object

    def create_user_dir(self):
        import shutil

        from . import templates

        super().create_user_dir()
        for template in templates:
            dest = self.user_dir.joinpath(template.name)
            if dest.exists():
                continue
            shutil.copyfile(template, dest)

    def add_show_command(self, show_cmd):
        @show_cmd.command(
            name=self.group_name,
            aliases=self.cmd_aliases,
        )
        @click.argument(
            "name",
            metavar="name",
            required=False,
            default="",
            callback=lambda ctx, param, val: val.lower(),
        )
        @click.option(
            "-t",
            "--type",
            "filter_types",
            multiple=True,
            type=click.Choice(
                self.cf_types.keys(),
                case_sensitive=False,
            ),
        )
        def _show(name, filter_types=None):
            # filter cf object lists by selected filter types
            object_items = [
                (
                    top_level_key,
                    sorted(
                        cf_objects.values(),
                        # sort alpha on name, with builtin all first
                        key=lambda x: (not x.is_builtin, x.name),
                    ),
                )
                for top_level_key, cf_objects in self.items()
                if not filter_types or top_level_key in filter_types
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
                        click.echo("")
                    click.secho(f"[{tlk}]", fg="green")
                    for element in els:
                        element.list_display()
            elif not name:
                logger.error(
                    "Cannot show %s: none found",
                    self.group_display_name,
                )
            else:
                logger.error(
                    "Cannot show %s: no matches for '%s'",
                    self.group_display_name,
                    name,
                )


class BaseCFObject(metaclass=CFObjectMeta):
    """Base class for all cloudformation types."""

    abstract = True

    def __init__(
        self,
        name,
        definition,
        path: Path = None,
        project=None,
        parent_component=None,
        source: str = None,
    ) -> None:
        self.name = name
        self.definition = definition
        self.path = path
        self.resource_type = definition.get("Type", None)
        self.project = project
        self.parent_component = parent_component

        self.source = source
        if self.parent_component:
            parent_source = (
                f" [{self.parent_component.source}]"
                if self.parent_component.source
                else ""
            )
            self.source = f"task {self.parent_component.name}{parent_source}"

        self.is_builtin = self.source == BUILT_IN

    @property
    def display_source(self):
        return self.source if self.source else misc.relative_to_cwd(self.path)

    def make_display_name(self, show_type=True):
        show_type = show_type and self.resource_type
        return "{}{} ({})".format(
            self.name,
            f" [{self.resource_type}]" if show_type else "",
            self.display_source,
        )

    @property
    def display_name(self):
        return self.make_display_name()

    def list_display(self, show_type=True):
        click.secho(self.make_display_name(show_type=show_type), fg="blue")

    def detail_display(self):
        self.list_display(show_type=False)
        click.echo(f"{self.top_level_key}:")
        click.echo(f"  {self.name}:")
        click.echo(
            textwrap.indent(
                self.definition.to_yaml(),
                "    ",
            )
        )


class CFObject(BaseCFObject):
    """Used as a class to instantiate all other CF object classes
    via class resolution to find the relevant CF object type from
    the provided top_level_key.
    """

    abstract = True

    def __new__(cls, top_level_key, *args, **kwargs):
        cls = cls.resolve_cls(top_level_key)
        return cls(*args, **kwargs)


class CloudFormation(metaclass=CFObjectMeta):
    """Used as the group added to Groups.
    Tracks all cloudformation objects of other types.
    """

    abstract = True
    group_name = "cloudformation"
    group_display_name = "CloudFormation"
    cmd_aliases = ["cf"]
    user_extendable = True
