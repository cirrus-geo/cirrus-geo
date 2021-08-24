from .. import files
from ..base import Lambda
from cirrus.cli.collection import Collection


class Feeder(Lambda):
    python = files.Python(name='feeder.py')
    definition = files.Definition()
    # make this optional once we have them
    readme = files.Readme(optional=True)


feeders = Collection(
    'feeders',
    Feeder,
)