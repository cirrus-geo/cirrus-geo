from pathlib import Path

from cirrus.cli import component


class Feeder(component.Lambda):
    python = component.ComponentFile(filename='feeder.py', content_fn=lambda x: '')
    definition = component.ComponentFile(filename='definition.yml', content_fn=lambda x: '')
    # make this optional once we have them
    readme = component.ComponentFile(filename='README.md', optional=True, content_fn=lambda x: '')
