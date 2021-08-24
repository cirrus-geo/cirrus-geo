import logging

from .component import Component
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class StepFunction(Component):
    def load_config(self):
        self.config = NamedYamlable.from_yaml(self.definition.content)
        try:
            self.description = self.config.definition.Comment
        except AttributeError:
            pass

    # TODO: same as the note on lambdas above, may make more sense
    # to have default files declared here and methods on the class
    # that can be overriden to provide default content
    @property
    def definition(self):
        raise NotImplementedError("Must define a file named 'definition'")
