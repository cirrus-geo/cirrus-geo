import logging

from pathlib import Path

from cirrus.core.constants import (
    DEFAULT_CONFIG_FILENAME,
    SERVERLESS_PLUGINS,
)
from cirrus.core.exceptions import ConfigError
from cirrus.core.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


DEFAULT_CONFIG_PATH = Path(__file__).parent.joinpath('default.yml')


class Config(NamedYamlable):
    @classmethod
    def default(cls):
        return cls.from_file(DEFAULT_CONFIG_PATH)

    @classmethod
    def from_project(cls, project):
        return cls.from_file(
            project.path.joinpath(DEFAULT_CONFIG_FILENAME),
        )

    def validate(self) -> None:
        # set defaults
        self.functions = {}
        self.stepFunctions = dict(validate=True, stateMachines={})
        self.resources = dict(
            Description='Cirrus STAC Processing Framework',
            Resources={},
            Outputs={},
        )

        self.package = {}
        self.package.individually = True
        self.package.exclude = []
        self.package.exclude.append('**/*')

        # populate required plugin list
        try:
            self.plugins.extend(SERVERLESS_PLUGINS.keys())
        except AttributeError:
            self.plugins = list(SERVERLESS_PLUGINS.keys())
        else:
            # deduplicate
            self.plugins = list(set(self.plugins))

    def build(self, groups):
        # add all components and resources
        copy = self.copy()
        for group in groups:
            copy.register(group)
        return copy

    def register(self, group) -> None:
        from cirrus.core.components.base import Lambda, StepFunction
        from cirrus.core.resources import Resource, Output
        if issubclass(group, Lambda):
            self.register_lambda_group(group)
        elif issubclass(group, StepFunction):
            self.register_step_function_group(group)
        elif issubclass(group, Resource):
            self.resources.Resources = {e.name: e.definition for e in group.values()}
        elif issubclass(group, Output):
            self.resources.Outputs = {e.name: e.definition for e in group.values()}
        else:
            raise ConfigError(
                f"Unable to register group '{group.name}': unknown type '{group.type}'",
            )

    def register_lambda_group(self, lambda_group) -> None:
        for lambda_component in lambda_group.values():
            self.register_lambda(lambda_component)

    def register_lambda(self, lambda_component) -> None:
        if not lambda_component.lambda_enabled:
            logging.debug(
                "Skipping disabled lambda: '%s'",
                lambda_component.display_name,
            )
            return

        if lambda_component.name in self.functions and not lambda_component.is_core_component:
            logging.warning(
                "Duplicate lambda declaration: '%s', skipping",
                lambda_component.display_name,
            )
            return

        self.functions[lambda_component.name] = lambda_component.lambda_config

    def register_step_function_group(self, sf_group) -> None:
        for sf_component in sf_group.values():
            self.register_step_function(sf_component)

    def register_step_function(self, sf_component) -> None:
        if not sf_component.enabled:
            logging.debug(
                "Skipping disabled step function: '%s'",
                sf_component.display_name,
            )
            return

        if sf_component.name in self.stepFunctions.stateMachines and not sf_component.is_core_component:
            logging.warning(
                f"Duplicate step function declaration '{sf_component.display_name}', skipping",
            )
            return
        self.stepFunctions.stateMachines[sf_component.name] = sf_component.config
