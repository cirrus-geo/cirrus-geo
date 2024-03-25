from collections.abc import Iterator

try:
    from importlib.metadata import EntryPoint, entry_points
except ImportError:
    from importlib_metadata import EntryPoint, entry_points

PLUGIN_GROUP = "cirrus.plugins"
COMMANDS_GROUP = "cirrus.commands"
RESOURCES_GROUP = "cirrus.resources"


def iter_entry_points(group_name: str) -> Iterator[EntryPoint]:
    def sorter(ep):
        # we want to ensure built-ins
        # are always loaded first
        if ep.name == "built-in":
            # null is the "lowest" char
            return "\0"
        return ep.name

    ep_collection = entry_points()
    if hasattr(ep_collection, "select"):
        # python 3.10 and forward
        eps = list(ep_collection.select(group=group_name))
    elif type(ep_collection) is dict:
        # python 3.9 and backward
        eps = list(ep_collection.get(group_name, []))
    else:
        raise RuntimeError(
            f"Unknown type returned from entry_points {type(ep_collection)}"
        )
    eps.sort(key=sorter)
    yield from eps


def iter_plugins() -> Iterator[EntryPoint]:
    yield from iter_entry_points(PLUGIN_GROUP)


def iter_resources() -> Iterator[EntryPoint]:
    yield from iter_entry_points(RESOURCES_GROUP)
