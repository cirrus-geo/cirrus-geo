from pathlib import Path

from cirrus.cli import resource


class CoreTask(resource.ResourceBase):
    enable_cli = False
    python = resource.ResourceFile(filename='task.py')
    definition = resource.ResourceFile(filename='definition.yml')
    # make this optional once we have them
    readme = resource.ResourceFile(filename='README.md', optional=True)
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)
