import logging

from collections.abc import Sequence

from cirrus.core.components import (
    Lambda,
    StepFunction,
    Function,
    Feeder,
    Task,
    Workflow,
)
from cirrus.core.cloudformation import CloudFormation


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

    @property
    def lambda_groups(self):
        return [c for c in self.groups if issubclass(c, Lambda)]

    @property
    def stepfunction_groups(self):
        return [c for c in self.groups if issubclass(c, StepFunction)]

    @property
    def cf_groups(self):
        return [c for c in self.groups if issubclass(c, BaseCFObject)]

    @property
    def extendable_groups(self):
        return [c for c in self.groups if c.user_extendable]

    def register_group(self, group):
        setattr(self, group.group_name, group)
        group.register_parent(self)
        group.register_project(self.project)

    def register_project(self, project):
        self.project = project
        for group in self.groups:
            group.register_project(self.project)


def make_groups(project=None):
    return Groups(
        Function,
        Feeder,
        Task,
        Workflow,
        CloudFormation,
        project=project,
    )
