from pathlib import Path

from .. import files
from ..base import StepFunction


class Workflow(StepFunction):
    definition = files.Definition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)
