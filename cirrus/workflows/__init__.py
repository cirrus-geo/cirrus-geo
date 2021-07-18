from pathlib import Path

from cirrus import resource
from cirrus.config import config


DEFAULT_INCLUDE = Path(__file__).parent.joinpath('config')


class Workflow(resource.ResourceBase):
    required_files = [
        resource.Definition,
    ]
    optional_files = [
        # TODO: Readme should be required
        # once we have one per workflow
        resource.Readme,
    ]


def print_workflows():
    workflows = []
    for _dir in [DEFAULT_INCLUDE]: # + config.sources.workflows:
        workflows.extend(resource.get_resources_from_dir(_dir, Workflow))

    for workflow in workflows:
        print(workflow.name)


if __name__ == '__main__':
    print_workflows()
