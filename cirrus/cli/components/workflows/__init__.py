from .. import files
from ..base import StepFunction
from cirrus.cli.collection import Collection


class Workflow(StepFunction):
    definition = files.StepFunctionDefinition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)


workflows = Collection(
    'workflows',
    Workflow,
)
