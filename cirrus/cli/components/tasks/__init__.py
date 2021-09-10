from .. import files
from ..base import Lambda
from cirrus.cli.collection import Collection


class Task(Lambda):
    handler = files.PythonHandler()
    definition = files.LambdaDefinition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)


tasks = Collection(
    'tasks',
    Task,
)
