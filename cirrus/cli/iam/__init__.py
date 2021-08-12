from pathlib import Path

from cirrus.cli.project import project
from cirrus.cli.utils.yaml import NamedYamlable


def iam_resources():
    # order matters, we want to prefer the user's resources
    # so we can override the built-in definitions
    search_dirs = (
        Path(__file__).parent.joinpath('config'),
        project.path.joinpath('iam'),
    )
    for d in search_dirs:
        for yml in d.glob('*.yml'):
            yml = NamedYamlable.from_file(yml)
            try:
                # TODO: the IAM stuff changes in a newer
                # serverless release, and this will need
                # to be updated to the new format
                yield yml['iamRoleStatements']
            except KeyError:
                yield yml
