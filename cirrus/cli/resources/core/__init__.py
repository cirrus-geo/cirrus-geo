from pathlib import Path

from cirrus.cli.project import project
from cirrus.cli.utils.yaml import NamedYamlable


def core_resources():
    # order matters, we want to prefer the user's resources
    # so we can override the built-in definitions
    search_dirs = (
        Path(__file__).parent.joinpath('config'),
        project.path.joinpath('resources'),
    )
    for d in search_dirs:
        for yml in d.glob('*.yml'):
            yml = NamedYamlable.from_file(yml)
            try:
                yield yml['Resources']
            except KeyError:
                yield yml
