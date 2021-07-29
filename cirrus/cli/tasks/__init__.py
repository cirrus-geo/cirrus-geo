from pathlib import Path

from cirrus.cli import resource


# TODO: batch-jobs.yml


class Task(resource.ResourceBase):
    task_py = resource.ResourceFile(filename='task.py')
    definition = resource.ResourceFile(filename='definition.yml')
    # TODO: Readme should be required once we have one per task
    readme = resource.ResourceFile(filename='README.md', optional=True)
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)
