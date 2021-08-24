from .. import files
from ..base import Lambda
from cirrus.cli.collection import Collection


class Task(Lambda):
    python = files.Python()
    definition = files.Definition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)


tasks = Collection(
    'tasks',
    Task,
)
