from pathlib import Path

from cirrus.cli import resource
from cirrus.cli.project import project
from cirrus.cli.utils.yaml import NamedYamlable


class CoreTask(resource.ResourceBase):
    enable_cli = False
    user_extendable = False
    python = resource.ResourceFile(filename='task.py', content_fn=lambda x: '')
    definition = resource.ResourceFile(filename='definition.yml', content_fn=lambda x: '')
    # make this optional once we have them
    readme = resource.ResourceFile(filename='README.md', optional=True)
    requirements = resource.ResourceFile(filename='requirements.txt', optional=True)


def core_resources():
    search_dirs = []
    for d in (CoreTask.core_dir, project.path.joinpath('custom')):
        for yml in d.glob('*.yml'):
            yml = NamedYamlable.from_file(yml)
            try:
                yield yml['Resources']
            except KeyError:
                yield yml
