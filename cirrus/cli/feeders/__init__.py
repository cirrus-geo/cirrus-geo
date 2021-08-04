from pathlib import Path

from cirrus.cli import resource


class Feeder(resource.ResourceBase):
    python = resource.ResourceFile(filename='feeder.py', content_fn=lambda x: '')
    definition = resource.ResourceFile(filename='definition.yml', content_fn=lambda x: '')
    # make this optional once we have them
    readme = resource.ResourceFile(filename='README.md', optional=True, content_fn=lambda x: '')
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)
