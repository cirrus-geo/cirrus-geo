import logging

from pathlib import Path
from cirrus.cli.constants import (
    DEFAULT_CONFIG_FILENAME,
    SERVERLESS_PLUGINS,
)
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


DEFAULT_CONFIG_PATH = Path(__file__).parent.joinpath('default.yml')


class Config(NamedYamlable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def default(cls):
        return cls.from_file(DEFAULT_CONFIG_PATH)

    @classmethod
    def from_project(cls, project):
        self = cls.from_file(
            project.path.joinpath(DEFAULT_CONFIG_FILENAME),
        )

        # add all lambda functions
        function_types = (project.core_tasks, project.tasks, project.feeders)
        for ftype in function_types:
            for fn in ftype:
                self.register_function(fn)

        # add all state machine step functions
        for workflow in project.workflows:
            self.register_workflow(workflow)

        # include core and custom resource files
        self.register_resources(project.core_resources)

        return self

    @classmethod
    def from_file(cls, file: Path):
        self = cls.from_file(file)

        # set defaults
        self.functions = {}
        self.stepFunctions = dict(validate=True, stateMachines={})
        self.resources = dict(
            Description='Cirrus STAC Processing Framework',
            Resources={},
        )

        # populate required plugin list
        try:
            self.plugins.extend(SERVERLESS_PLUGINS.keys())
        except AttributeError:
            self.plugins = serverless_plugins.keys()
        else:
            # deduplicate
            self.plugins = list(set(self.plugins))

        return self

    def register_function(self, lambda_component) -> None:
        if lambda_component.name in self.functions and not lambda_component.is_core_component:
            logging.warning(
                f"Duplicate function declaration: '{lambda_component.display_name}', skipping",
            )
            return
        self.functions[lambda_component.name] = lambda_component.config

    def register_workflow(self, workflow) -> None:
        if workflow.name in self.stepFunctions.stateMachines and not workflow.is_core_component:
            logging.warning(
                f"Duplicate workflow declaration '{workflow.display_name}', skipping",
            )
            return
        self.stepFunctions.stateMachines[workflow.name] = workflow.config

    def register_resources(self, resources) -> None:
        self.resources.Resources = resources
