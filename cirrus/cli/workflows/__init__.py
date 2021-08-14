from pathlib import Path

from cirrus.cli.component import files, StepFunction


class Workflow(StepFunction):
    definition = files.Definition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)
