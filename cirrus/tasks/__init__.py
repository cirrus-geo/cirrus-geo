from pathlib import Path

from cirrus import resource
from cirrus.config import config


DEFAULT_INCLUDE = Path(__file__).parent.joinpath('config')


class TaskPython(resource.ResourceFileBase):
    filename = 'task.py'


class Task(resource.ResourceBase):
    required_files = [
        resource.Definition,
        TaskPython,
    ]
    optional_files = [
        # TODO: Readme should be required
        # once we have one per workflow
        resource.Readme,
        resource.Requirements,
    ]


def print_tasks():
    tasks = []
    for _dir in [DEFAULT_INCLUDE]: # + config.sources.tasks:
        tasks.extend(resource.get_resources_from_dir(_dir, Task))

    for task in tasks:
        print(task.name)


if __name__ == '__main__':
    print_tasks()
