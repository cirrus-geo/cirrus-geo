from ..base import StepFunction
from cirrus.cli.collection import Collection


class Workflow(StepFunction):
    pass


workflows = Collection(
    'workflows',
    Workflow,
)
