import logging

from collections.abc import Sequence

from cirrus.cli.components import (
    Lambda,
    StepFunction,
    Function,
    Feeder,
    Task,
    Workflow,
)
from cirrus.cli.resources import BaseResource, Resource, Output


logger = logging.getLogger(__name__)


class Collections(Sequence):
    def __init__(self, *collections, project=None):
        self.collections = collections
        self.project = project

        for collection in self.collections:
            self.register_collection(collection)

    def __len__(self):
        return len(self.collections)

    def __getitem__(self, index):
        return self.collections[index]

    @property
    def lambda_collections(self):
        return [c for c in self.collections if issubclass(c, Lambda)]

    @property
    def stepfunction_collections(self):
        return [c for c in self.collections if issubclass(c, StepFunction)]

    @property
    def resource_collections(self):
        return [c for c in self.collections if issubclass(c, BaseResource)]

    @property
    def extendable_collections(self):
        return [c for c in self.collections if c.user_extendable]

    def register_collection(self, collection):
        setattr(self, collection.collection_name, collection)
        collection.parent = self
        collection.register_project(self.project)

    def register_project(self, project):
        self.project = project
        for collection in self.collections:
            collection.register_project(self.project)


def make_collections(project=None):
    return Collections(
        Function,
        Feeder,
        Task,
        Workflow,
        Resource,
        Output,
        project=project,
    )
