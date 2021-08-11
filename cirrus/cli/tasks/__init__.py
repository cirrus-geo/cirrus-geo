from pathlib import Path

from cirrus.cli import component


class Task(component.Lambda):
    task_py = component.ComponentFile(filename='task.py', content_fn=lambda x: '')
    definition = component.ComponentFile(filename='definition.yml', content_fn=lambda x: '')
    # TODO: Readme should be required once we have one per task
    readme = component.ComponentFile(filename='README.md', optional=True, content_fn=lambda x: '')
    requirements = component.ComponentFile(filename='requirements.txt', optional=True)
