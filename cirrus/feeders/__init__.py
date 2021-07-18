from pathlib import Path

from cirrus import resource
from cirrus.config import config


DEFAULT_INCLUDE = Path(__file__).parent.joinpath('config')


class FeederPython(resource.ResourceFileBase):
    filename = 'feeder.py'


class Feeder(resource.ResourceBase):
    required_files = [
        resource.Definition,
        resource.Readme,
        FeederPython,
    ]
    optional_files = [
        resource.Requirements,
    ]


def print_feeders():
    feeders = []
    for _dir in [DEFAULT_INCLUDE]: # + config.sources.feeders:
        feeders.extend(resource.get_resources_from_dir(_dir, Feeder))

    for feeder in feeders:
        print(feeder.name)


if __name__ == '__main__':
    print_feeders()
