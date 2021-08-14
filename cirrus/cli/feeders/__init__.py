from pathlib import Path

from cirrus.cli.component import files, Lambda


class Feeder(Lambda):
    python = files.Python(name='feeder.py')
    definition = files.Definition()
    # make this optional once we have them
    readme = files.Readme(optional=True)
