import logging
from pathlib import Path
from typing import Type, TypeVar

import click

from cirrus.core.constants import BUILT_IN
from cirrus.core.exceptions import ComponentError
from cirrus.core.group_meta import GroupMeta
from cirrus.core.utils import misc
from cirrus.core.utils.yaml import NamedYamlable

from ..files import BaseDefinition, ComponentFile

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Component")


class ComponentMeta(GroupMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        files = attrs.get("files", {})

        # copy file attrs to files
        for attr_name, attr in attrs.items():
            if isinstance(attr, ComponentFile):
                files[attr_name] = attr

        # copy parent class files to child,
        # if not overridden on child
        for base in bases:
            if hasattr(base, "files"):
                for fname, f in base.files.items():
                    if fname not in attrs:
                        attrs[fname] = f
                        files[fname] = f

        attrs["files"] = files

        if "user_extendable" not in attrs:
            attrs["user_extendable"] = True

        return super().__new__(cls, name, bases, attrs, **kwargs)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type = self.__name__.lower()

    def from_dir(self, d: Path, name: str = None, source: str = None) -> Type[T]:
        if not d.is_dir():
            return

        for component_dir in sorted(d.resolve().iterdir()):
            if component_dir.name.startswith("."):
                continue
            if component_dir.name in ("__init__.py", "__pycache__"):
                continue
            if name and component_dir.name != name:
                continue
            try:
                yield self(component_dir, source=source)
            except ComponentError as e:
                logger.warning(
                    f"Skipping {self.type} '{component_dir.name}': {e}",
                )
                continue

    def _find(self, name: str = None) -> Type[T]:
        for plugin_name, plugin_dir in self.plugins.items():
            yield from self.from_dir(plugin_dir, name=name, source=plugin_name)

        if self.user_dir and self.user_dir.is_dir():
            yield from self.from_dir(self.user_dir, name=name)

    def find(self):
        self._elements = {}
        for element in self._find():
            if element.name in self._elements:
                logger.warning(
                    "Duplicate %s declaration '%s', overriding",
                    self.type,
                    element.name,
                )
            self._elements[element.name] = element

    def extra_create_args(self):
        def wrapper(func):
            return func

        return wrapper

    def add_create_command(self, create_cmd):
        if not (self.enable_cli and self.user_extendable):
            return

        @create_cmd.command(name=self.type)
        @click.argument(
            "name",
            metavar="name",
        )
        @click.argument(
            "description",
            metavar="description",
        )
        @self.extra_create_args()
        def _create(name, description, **kwargs):
            import sys

            try:
                self.create(name, description, **kwargs)
            except ComponentError as e:
                logger.error(e)
                sys.exit(1)
            else:
                # TODO: logging level for "success" on par with warning?
                click.secho(
                    f"{self.type} {name} created",
                    err=True,
                    fg="green",
                )

    def add_show_command(self, show_cmd):
        if not self.enable_cli:
            return

        @show_cmd.command(name=self.group_name, aliases=self.cmd_aliases)
        @click.argument(
            "name",
            metavar="name",
            required=False,
        )
        @click.argument(
            "filename",
            metavar="filename",
            required=False,
        )
        def _show(name=None, filename=None):
            if name is None:
                for element in self.values():
                    element.list_display()
                return

            try:
                element = self[name]
            except KeyError:
                logger.error("Cannot show: unknown %s '%s'", self.type, name)
                return

            if filename is None:
                element.detail_display()
                return

            try:
                element.files[filename].show()
            except KeyError:
                logger.error("Cannot show: unknown file '%s'", filename)


class Component(metaclass=ComponentMeta):
    definition = BaseDefinition()

    def __init__(
        self, path: Path, description: str = "", load: bool = True, source: str = None
    ) -> None:
        self.path = path
        self.name = path.name
        self.config = None
        self.description = description
        self.source = source
        self.is_builtin = source == BUILT_IN

        self.files = {}
        for fname, f in self.__class__.files.items():
            f.copy_to_component(self, fname)

        self._loaded = False
        if load:
            self._load()

    def relative_path(self):
        return misc.relative_to_cwd(self.path)

    @property
    def enabled(self):
        return self._enabled

    def display_attrs(self):
        if not self.enabled:
            yield "DISABLED"
        if self.source:
            yield self.source

    @property
    def display_name(self):
        attrs = list(self.display_attrs())
        return "{}{}".format(
            self.name,
            " ({})".format(", ".join(attrs)) if attrs else "",
        )

    def _load(self, init_files=False):
        if not self.path.is_dir():
            raise ComponentError(
                f"Cannot load {self.type} from '{self.relative_path()}': not a directory."
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
        self.config = NamedYamlable.from_yaml(self.definition.content)
        self._enabled = self.config.pop("enabled", True)

    def _create_do(self):
        if self._loaded:
            raise ComponentError(f"Cannot create a loaded {self.__class__.__name__}.")

        self.path.parent.mkdir(exist_ok=True)

        try:
            self.path.mkdir()
        except FileExistsError as e:
            raise ComponentError(
                f"Cannot create {self.__class__.__name__} at '{self.relative_path()}': already exists."
            ) from e

        try:
            self._load(init_files=True)
        except Exception:
            # want to clean up anything
            # we created if we failed
            import shutil

            try:
                shutil.rmtree(self.path)
            except FileNotFoundError:
                pass
            raise

    @classmethod
    def _create_init(cls, name: str, description: str) -> Type[T]:
        if not cls.user_extendable:
            raise ComponentError(f"Component {cls.type} does not support creation")
        path = cls.user_dir.joinpath(name)
        return cls(path, description, load=False)

    @classmethod
    def create(cls, name: str, description: str) -> Type[T]:
        new = cls._create_init(name, description)
        new._create_do()
        return new

    def list_display(self):
        color = "blue" if self.enabled else "red"
        click.echo(
            "{}{}".format(
                click.style(
                    f"{self.display_name}:",
                    fg=color,
                ),
                f" {self.description}" if self.description else "",
            )
        )

    def detail_display(self):
        color = "blue" if self.enabled else "red"
        click.secho(self.display_name, fg=color)
        if self.description:
            click.echo(self.description)
        click.echo("\nFiles:")
        for name, f in self.files.items():
            click.echo(
                "  {}: {}".format(
                    click.style(name, fg="yellow"),
                    f.name,
                )
            )
