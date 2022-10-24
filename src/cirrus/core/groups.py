import logging
from collections.abc import Sequence

from cirrus.core.cloudformation import CloudFormation
from cirrus.core.components import (
    Feeder,
    Function,
    Lambda,
    StepFunction,
    Task,
    Workflow,
)

logger = logging.getLogger(__name__)


class Groups(Sequence):
    def __init__(self, *groups, parent=None, project=None):
        self.groups = groups
        self.parent = parent
        self.project = project

        for group in self.groups:
            self.register_group(group)

    def __len__(self):
        return len(self.groups)

    def __getitem__(self, index):
        return self.groups[index]

    def _yield_type(self, _type):
        yield from (c for g in self.groups if issubclass(g, _type) for c in g)

    @property
    def lambdas(self):
        yield from self._yield_type(Lambda)

    @property
    def stepfunctions(self):
        yield from self._yield_type(StepFunction)

    @property
    def cf_objects(self):
        yield from self._yield_type(CloudFormation)

    @property
    def extendable_groups(self):
        for group in self.groups:
            if group.user_extendable:
                yield group

    def register_group(self, group):
        setattr(self, group.group_name, group)
        group.register_parent(self)
        group.register_project(self.project)

    def register_project(self, project):
        self.project = project
        for group in self.groups:
            group.register_project(self.project)

    def ensure_created(self):
        for group in self.extendable_groups:
            group.ensure_created()


def make_groups(project=None):
    return Groups(
        Function,
        Feeder,
        Task,
        Workflow,
        CloudFormation,
        project=project,
    )
