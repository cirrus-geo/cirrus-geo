from .. import files
from ..base import Lambda
from cirrus.cli.collection import Collection


class CoreTask(Lambda):
    user_extendable = False
    display_type = 'Core Task'

    handler = files.PythonHandler()
    definition = files.LambdaDefinition()
    # make this not optional once we have them
    readme = files.Readme(optional=True)


core_tasks = Collection(
    'core-tasks',
    CoreTask,
    display_name='Core Tasks',
)
