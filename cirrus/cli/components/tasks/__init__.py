from pathlib import Path

from .. import files
from ..base import Lambda


class Task(Lambda):
    python = files.Python()
    definition = files.Definition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)
