from pathlib import Path

from cirrus.cli.component import Lambda, files


class Task(Lambda):
    python = files.Python()
    definition = files.Definition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)
