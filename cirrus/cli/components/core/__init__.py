from ..base import Lambda
from cirrus.cli.collection import Collection


class CoreTask(Lambda):
    user_extendable = False
    display_type = 'Core Task'


core_tasks = Collection(
    'core-tasks',
    CoreTask,
    display_name='Core Tasks',
)
