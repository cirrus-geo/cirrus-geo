from pathlib import Path

from cirrus import resource
from cirrus.config import config


DEFAULT_INCLUDE = Path(__file__).parent.joinpath('config')


class Feeder(resource.ResourceBase):
    default_search_dir = DEFAULT_INCLUDE
    python = resource.ResourceFile(filename='feeder.py')
    definition = resource.ResourceFile(filename='definition.yml')
    readme = resource.ResourceFile(filename='README.md')
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)


def print_feeders():
    feeders = []
    for _dir in [DEFAULT_INCLUDE]: # + config.sources.feeders:
        feeders.extend(Feeder.from_dir(_dir))

    for feeder in feeders:
        print(feeder.name)


if __name__ == '__main__':
    print_feeders()
