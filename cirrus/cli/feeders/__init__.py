from pathlib import Path

from cirrus.cli import resource


class Feeder(resource.ResourceBase):
    python = resource.ResourceFile(filename='feeder.py', content_fn=lambda x: '')
    definition = resource.ResourceFile(filename='definition.yml', content_fn=lambda x: '')
    readme = resource.ResourceFile(filename='README.md', content_fn=lambda x: '')
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)
