try:
    from importlib.metadata import entry_points
except:
    from importlib_metadata import entry_points


PLUGIN_GROUP = 'cirrus.plugins'
COMMANDS_GROUP = 'cirrus.commands'
RESOURCES_GROUP = 'cirrus.resources'


def iter_entry_points(group_name):
    yield from entry_points().get(group_name, [])


def iter_plugins():
    yield from iter_entry_points(PLUGIN_GROUP)


def iter_resources():
    yield from iter_entry_points(RESOURCES_GROUP)
