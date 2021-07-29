from pathlib import Path

from cirrus.cli import resource


class Feeder(resource.ResourceBase):
    python = resource.ResourceFile(filename='feeder.py')
    definition = resource.ResourceFile(filename='definition.yml')
    readme = resource.ResourceFile(filename='README.md')
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)
