from pathlib import Path

from .. import files
from ..base import Lambda


class Feeder(Lambda):
    python = files.Python(name='feeder.py')
    definition = files.Definition()
    # make this optional once we have them
    readme = files.Readme(optional=True)
