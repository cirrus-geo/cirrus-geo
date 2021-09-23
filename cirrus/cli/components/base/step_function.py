import logging

from .. import files
from .component import Component
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class StepFunction(Component):
    definition = files.StepFunctionDefinition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)

    def load_config(self):
        super().load_config()
        self.config = NamedYamlable.from_yaml(self.definition.content)
        try:
            self.description = self.config.definition.Comment
        except AttributeError:
            pass
