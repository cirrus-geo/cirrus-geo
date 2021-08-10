from pathlib import Path

from cirrus.cli import component


class Workflow(component.ComponentBase):
    definition = component.ComponentFile(filename='definition.yml', content_fn=lambda x: '')
    # TODO: Readme should be required once we have one per task
    readme = component.ComponentFile(filename='README.md', optional=True, content_fn=lambda x: '')

    def process_config(self):
        try:
            self.description = self.config.definition.Comment
        except AttributeError:
            pass
