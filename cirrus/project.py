from typing import List, TypeVar
from pathlib import Path

from cirrus.config import Config, DEFAULT_CONFIG_YML
from cirrus.feeders import Feeder
from cirrus.tasks import Task
from cirrus.workflows import Workflow


DEFAULT_CONFIG_FILENAME = 'cirrus.yml'


T = TypeVar('T', bound='Project')
class Project:
    def __init__(self,
                 config: Config,
                 feeders: List[Feeder],
                 tasks: List[Task],
                 workflows: List[Workflow]) -> None:
        self.config = config
        self.feeders = feeders
        self.tasks = tasks
        self.workflows = workflows

    # not sure if this makes sense
    # maybe just need from_config method
    @classmethod
    def from_dir(cls, d: Path) -> T:
        yaml = d.joinpath(DEFAULT_CONFIG_FILENAME).read_text(encoding='utf=8')
        config = Config.from_yaml(yaml)
        feeders = Feeder.find(config)
        tasks = Task.find(config)
        workflows = Workflow.find(config)
        return cls(config, feeders, tasks, workflows)

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
