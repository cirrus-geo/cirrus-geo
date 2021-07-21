import os
import click

from typing import List, TypeVar
from pathlib import Path

from cirrus.constants import DEFAULT_CONFIG_FILENAME
from cirrus.config import Config, DEFAULT_CONFIG_YML
from cirrus.feeders import Feeder
from cirrus.tasks import Task
from cirrus.workflows import Workflow


T = TypeVar('T', bound='Project')
class Project:
    def __init__(self,
                 config: Config,
                 feeders: List[Feeder]=None,
                 tasks: List[Task]=None,
                 workflows: List[Workflow]=None) -> None:
        self.config = config
        self._feeders = feeders
        self._tasks = tasks
        self._workflows = workflows

    @property
    def feeders(self):
        if self._feeders is None:
            self._feeders = Feeder.find(self.config)
        return self._feeders

    @property
    def tasks(self):
        if self._tasks is None:
            self._tasks = Task.find(self.config)
        return self._tasks

    @property
    def workflows(self):
        if self._workflows is None:
            self._workflows = Workflow.find(self.config)
        return self._workflows

    # not sure if this makes sense
    # maybe just need from_config method
    @classmethod
    def from_dir(cls, d: Path) -> T:
        yaml = d.joinpath(DEFAULT_CONFIG_FILENAME).read_text(encoding='utf=8')
        config = Config.from_yaml(yaml)
        return cls(config)

    @staticmethod
    def new(d: Path) -> None:
        for resource in ('feeders', 'tasks', 'workflows'):
            d.joinpath(resource).mkdir(exist_ok=True)

        conf = d.joinpath(DEFAULT_CONFIG_FILENAME)
        try:
            conf.touch()
        except FileExistsError:
            pass
        else:
            conf.write_text(DEFAULT_CONFIG_YML)


@click.command()
@click.argument(
    'directory',
    required=False,
    default=None,
    type=click.Path(
        exists=True,
        file_okay=False,
        writable=True,
        resolve_path=True,
        path_type=Path,
    ),
)
def init(directory=None):
    '''
    Initialize a cirrus project in DIRECTORY.

    DIRECTORY defaults to the current working directory.
    '''
    if not directory:
        directory = Path(os.getcwd())
    Project.new(directory)
    click.secho(
        f"Succesfully initialized project in '{directory}'.",
        err=True,
        fg='green',
    )
