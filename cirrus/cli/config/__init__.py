import logging

from cirrus.cli.constants import (
    DEFAULT_CONFIG_FILENAME,
    SERVERLESS_PLUGINS,
)
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class Config(NamedYamlable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def from_project(cls, project):
        self = cls.from_file(
            project.path.joinpath(DEFAULT_CONFIG_FILENAME),
        )

        # set defaults
        self.functions = {}
        self.stepFunctions = dict(validate=True, stateMachines={})
        self.resources = dict(
            Description='Cirrus STAC Processing Framework',
            Resources={},
        )

        # populate required plugin list
        try:
            self.plugins.extend(SERVERLESS_PLUGINS)
        except AttributeError:
            self.plugins = SERVERLESS_PLUGINS
        else:
            # deduplicate
            self.plugins = list(set(self.plugins))

        # add all lambda functions
        function_types = (project.core_tasks, project.tasks, project.feeders)
        for ftype in function_types:
            for fn in ftype:
                self.register_function(fn)

        # add all state machine step functions
        for workflow in project.workflows:
            self.register_workflow(workflow)

        # include core and custom resource files
        for cr in project.core_resources:
            self.register_resources(cr)

        return self

    def register_function(self, lambda_resource) -> None:
        if lambda_resource.name in self.functions and not lambda_resource.is_core_resource:
            logging.warning(
                f"Duplicate function declaration: '{lambda_resource.display_name}', skipping",
            )
            return
        self.functions[lambda_resource.name] = lambda_resource.config

    def register_workflow(self, workflow) -> None:
        if workflow.name in self.stepFunctions.stateMachines and not workflow.is_core_resource:
            logging.warning(
                f"Duplicate workflow declaration '{workflow.display_name}', skipping",
            )
            return
        self.stepFunctions.stateMachines[workflow.name] = workflow.config

    def register_resources(self, resource_config: NamedYamlable) -> None:
        for resource, config in resource_config.items():
            if resource in self.resources.Resources:
                logging.warning(
                    f"Duplicate resource declaration '{resource}', overriding",
                )
            self.resources.Resources[resource] = config
