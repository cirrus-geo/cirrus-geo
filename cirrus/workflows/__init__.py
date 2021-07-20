from pathlib import Path

from cirrus import resource
from cirrus.config import config


DEFAULT_INCLUDE = Path(__file__).parent.joinpath('config')


class Workflow(resource.ResourceBase):
    default_search_dir = DEFAULT_INCLUDE
    definition = resource.ResourceFile(filename='definition.yml')
    # TODO: Readme should be required once we have one per task
    readme = resource.ResourceFile(filename='README.md', optional=True)


def print_workflows():
    workflows = []
    for _dir in [DEFAULT_INCLUDE]: # + config.sources.workflows:
        workflows.extend(Workflow.from_dir(_dir))

    for workflow in workflows:
        print(workflow.name)


if __name__ == '__main__':
    print_workflows()
