import logging
from abc import ABCMeta, abstractmethod
from collections.abc import MutableMapping
from pathlib import Path

from cirrus.core.utils.plugins import iter_resources

logger = logging.getLogger(__name__)


def resource_plugins(resource_type):
    plugins = {}
    for entrypoint in iter_resources():
        plugin_path = Path(entrypoint.load().__path__[0]).joinpath(resource_type)

        if not plugin_path.is_dir():
            continue

        plugins[entrypoint.name] = plugin_path

    return plugins


class GroupMeta(MutableMapping, ABCMeta):
    def __new__(cls, name, bases, attrs, **kwargs):
        if "group_name" not in attrs:
            attrs["group_name"] = f"{name.lower()}s"

        if "group_display_name" not in attrs:
            attrs["group_display_name"] = attrs["group_name"].capitalize()

        if "enable_cli" not in attrs:
            attrs["enable_cli"] = True

        if "cmd_aliases" not in attrs:
            attrs["cmd_aliases"] = []

        attrs["user_extendable"] = attrs.get("user_extendable", False)

        if not attrs["user_extendable"]:
            attrs["user_dir_name"] = None
        elif "user_dir_name" not in attrs or attrs["user_dir_name"] is None:
            attrs["user_dir_name"] = attrs["group_name"]

        attrs["_plugins"] = None
        attrs["_elements"] = None
        attrs["project"] = None
        attrs["parent"] = None

        return super().__new__(cls, name, bases, attrs, **kwargs)

    @classmethod
    def __subclasshook__(cls, c):
        if cls is GroupMeta:
            if any("elements" in b.__dict__ for b in c.__mro__):
                return True
            return False
        return NotImplemented

    def __hash__(cls):
        return hash(cls.group_name)

    @property
    def plugins(cls):
        if cls._plugins is None:
            cls._plugins = (
                resource_plugins(cls.group_name) if cls.user_extendable else {}
            )
        return cls._plugins

    @property
    def elements(cls):
        if cls._elements is None:
            cls.find()
        return cls._elements

    @property
    def user_dir(cls):
        if cls.user_dir_name is None:
            return None
        if cls.project is None or cls.project.path is None:
            logger.warning(
                f"No cirrus project specified; limited to {cls.group_display_name} built-in and from plugins.",
            )
            return None
        return cls.project.path.joinpath(cls.user_dir_name)

    @abstractmethod
    def find(cls):
        pass

    def reset_plugins(cls):
        cls._plugins = None

    def reset_elements(cls):
        cls._elements = None
        cls.reset_plugins()

    def register_parent(cls, parent):
        cls.parent = parent

    def register_project(cls, project):
        cls.project = project
        cls.reset_elements()

    def create_user_dir(cls):
        """Used on project init to create any default files.
        Useful for things that most projects require but shouldn't
        be managed by default by cirrus, e.g., cloudformation templates
        for S3 buckets."""
        cls.user_dir.mkdir(exist_ok=True)

    def ensure_created(cls):
        if not (cls.user_extendable and cls.user_dir):
            return False
        cls.create_user_dir()

    def items(cls):
        return cls.elements.items()

    def keys(cls):
        return cls.elements.keys()

    def values(cls):
        return cls.elements.values()

    def get(cls, *args, **kwargs):
        return cls.elements.get(*args, **kwargs)

    def __iter__(cls):
        return iter(cls.elements.values())

    def __len__(cls):
        return len(cls.elements)

    def __getitem__(cls, key):
        return cls.elements[key]

    def __setitem__(cls, key, val):
        cls.elements[key] = val

    def __delitem__(cls, key):
        del cls.elements[key]

    def __repr__(cls):
        return f"{type(cls).__qualname__}({repr(cls.elements)})"
