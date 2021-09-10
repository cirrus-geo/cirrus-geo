from ..base import Lambda
from cirrus.cli.collection import Collection


class Task(Lambda):
    pass


tasks = Collection(
    'tasks',
    Task,
)
