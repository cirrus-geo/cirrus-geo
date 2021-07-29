from pathlib import Path

from cirrus.cli import resource


class Workflow(resource.ResourceBase):
    definition = resource.ResourceFile(filename='definition.yml')
    # TODO: Readme should be required once we have one per task
    readme = resource.ResourceFile(filename='README.md', optional=True)
