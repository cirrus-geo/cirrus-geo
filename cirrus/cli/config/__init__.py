import logging

from pathlib import Path

from cirrus.cli.constants import (
    DEFAULT_CONFIG_FILENAME,
    SERVERLESS_PLUGINS,
)
from cirrus.cli.exceptions import ConfigError
from cirrus.cli.utils.yaml import NamedYamlable


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

    def build(self, collections):
        # add all components and resources
        copy = self.copy()
        for collection in collections:
            copy.register(collection)
        return copy

    def register(self, collection) -> None:
        from cirrus.cli.components.base import Lambda, StepFunction
        from cirrus.cli.resources import Resource, Output
        if issubclass(collection, Lambda):
            self.register_lambda_collection(collection)
        elif issubclass(collection, StepFunction):
            self.register_step_function_collection(collection)
        elif issubclass(collection, Resource):
            self.resources.Resources = {e.name: e.definition for e in collection.values()}
        elif issubclass(collection, Output):
            self.resources.Outputs = {e.name: e.definition for e in collection.values()}
        else:
            raise ConfigError(
                f"Unable to register collection '{collection.name}': unknown type '{collection.type}'",
            )

    def register_lambda_collection(self, lambda_collection) -> None:
        for lambda_component in lambda_collection.values():
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

    def register_step_function_collection(self, sf_collection) -> None:
        for sf_component in sf_collection.values():
            self.register_step_function(sf_component)

    def register_step_function(self, sf_component) -> None:
        if sf_component.name in self.stepFunctions.stateMachines and not sf_component.is_core_component:
            logging.warning(
                f"Duplicate step function declaration '{sf_component.display_name}', skipping",
            )
            return
        self.stepFunctions.stateMachines[sf_component.name] = sf_component.config
