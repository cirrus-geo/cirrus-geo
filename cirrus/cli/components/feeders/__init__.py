from ..base import Lambda
from cirrus.cli.collection import Collection


class Feeder(Lambda):
    pass


feeders = Collection(
    'feeders',
    Feeder,
)
