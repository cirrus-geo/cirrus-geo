import logging

from .. import files
from .component import Component

logger = logging.getLogger(__name__)


class StepFunction(Component):
    definition = files.StepFunctionDefinition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)
    user_extendable = False

    def load_config(self):
        super().load_config()
        try:
            self.description = self.config.definition.Comment
        except AttributeError:
            pass
