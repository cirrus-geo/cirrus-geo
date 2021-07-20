from pathlib import Path

from cirrus import resource
from cirrus.config import config


DEFAULT_INCLUDE = Path(__file__).parent.joinpath('config')


# TODO: batch-jobs.yml


class Task(resource.ResourceBase):
    default_search_dir = DEFAULT_INCLUDE
    task_py = resource.ResourceFile(filename='task.py')
    definition = resource.ResourceFile(filename='definition.yml')
    # TODO: Readme should be required once we have one per task
    readme = resource.ResourceFile(filename='README.md', optional=True)
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)


def print_tasks():
    tasks = []
    for _dir in [DEFAULT_INCLUDE]: # + config.sources.tasks:
        tasks.extend(Task.from_dir(_dir))

    for task in tasks:
        print(task.name)


if __name__ == '__main__':
    print_tasks()
