try:
    from importlib.metadata import entry_points
except ImportError:
    from importlib_metadata import entry_points


PLUGIN_GROUP = "cirrus.plugins"
COMMANDS_GROUP = "cirrus.commands"
RESOURCES_GROUP = "cirrus.resources"


def iter_entry_points(group_name):
    def sorter(ep):
        # we want to ensure built-ins
        # are always loaded first
        if ep.name == "built-in":
            # null is the "lowest" char
            return "\0"
        return ep.name

    eps = list(entry_points().get(group_name, []))
    eps.sort(key=sorter)
    yield from eps


def iter_plugins():
    yield from iter_entry_points(PLUGIN_GROUP)


def iter_resources():
    yield from iter_entry_points(RESOURCES_GROUP)
