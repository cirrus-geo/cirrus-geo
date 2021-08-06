import os
import yaml

from typing import List, TypeVar
from pathlib import Path

from cirrus.cli import utils
from cirrus.cli.constants import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_SERVERLESS_FILENAME,
    DEFAULT_BUILD_DIR_NAME,
    SERVERLESS_PLUGINS
)
from cirrus.cli.config import Config, DEFAULT_CONFIG
from cirrus.cli.exceptions import CirrusError
from cirrus.cli.utils.yaml import NamedYamlable


C = TypeVar('C', bound='cirrus.cli.core.CoreTask')
F = TypeVar('F', bound='cirrus.cli.feeders.Feeder')
T = TypeVar('T', bound='cirrus.cli.tasks.Task')
W = TypeVar('W', bound='cirrus.cli.workflows.Workflow')


class Project:
    def __init__(self,
                 d: Path=None,
                 config: Config=None,
                 core_tasks: List[F]=None,
                 feeders: List[F]=None,
                 tasks: List[T]=None,
                 workflows: List[W]=None,
                 ) -> None:
        self._config = config
        self._core_tasks = core_tasks
        self._feeders = feeders
        self._tasks = tasks
        self._workflows = workflows
        self._serverless = None
        self._dynamic_attrs = [k[1:] for k in self.__dict__.keys() if k.startswith('_')]
        # do this after dynamic attrs
        # as we don't want it included
        self._path = d

    def __repr__(self):
        name = self.__class__.__name__
        path = '[not loaded]' if self.path is None else self.path
        return f'<{name}: {path}>'

    def __getattr__(self, name: str):
        if self.path is None and name in self._dynamic_attrs:
            raise CirrusError(
                'Cirrus project path not set. Set the path before accessing dynamic attributes.'
            )
        # TODO: I'm confused why getattr stopped working and
        # now I'm using getattribute...
        return super().__getattribute__(name)

    @property
    def path(self) -> Path:
        if self._path is None:
            # TODO: convert to click logging
            utils.cli_only_secho(
                'No cirrus project specified; limited to built-in resources.',
                err=True,
                fg='yellow',
            )
            raise CirrusError('Cirrus project path not set. Project is not initialized.')
        return self._path

    @path.setter
    def path(self, p: Path) -> None:
        if not self.dir_is_project(p):
            raise CirrusError(
                f"Cannot set project path, does not appear to be vaild project: '{p}'",
            )
        self._path = p

    @property
    def config(self) -> Config:
        if self._config is None:
            # TODO: what happens if no config file?
            self._config = Config.from_file(
                self.path.joinpath(DEFAULT_CONFIG_FILENAME),
            )
        return self._config

    @property
    def serverless(self) -> Config:
        if self._serverless is None:
            # TODO: what happens if no serverless file?
            self._serverless = Config.from_file(
                self.path.joinpath(DEFAULT_SERVERLESS_FILENAME),
            )
            self._serverless.functions = Config()
            self._serverless.stepFunctions.stateMachines = Config()
        return self._serverless

    @property
    def core_tasks(self) -> List[C]:
        if self._core_tasks is None:
            from cirrus.cli.core import CoreTask
            self._core_tasks = list(CoreTask.find())
        return self._core_tasks

    @property
    def feeders(self) -> List[F]:
        if self._feeders is None:
            from cirrus.cli.feeders import Feeder
            self._feeders = list(Feeder.find())
        return self._feeders

    @property
    def tasks(self) -> List[T]:
        if self._tasks is None:
            from cirrus.cli.tasks import Task
            self._tasks = list(Task.find())
        return self._tasks

    @property
    def workflows(self) -> List[W]:
        if self._workflows is None:
            from cirrus.cli.workflows import Workflow
            self._workflows = list(Workflow.find())
        return self._workflows

    @property
    def build_dir(self) -> Path:
        return self.path.joinpath(DEFAULT_BUILD_DIR_NAME)

    def resolve(self, d: Path=Path(os.getcwd())):
        d = d.resolve()
        def dirs(d):
            yield d
            yield from d.parents
        for parent in dirs(d):
            if Project.dir_is_project(parent):
                self._path = parent
                return

    @staticmethod
    def dir_is_project(d: Path) -> bool:
        config = d.joinpath(DEFAULT_CONFIG_FILENAME)
        return config.is_file()

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
            conf.write_text(yaml.dump(DEFAULT_CONFIG))

    def build(self) -> None:
        from cirrus.cli.core import core_resources
        sls = self.serverless

        # TODO: refactor into convenience methods
        # add all lambda functions
        for task in self.core_tasks:
            if not hasattr(sls.functions, task.name):
                setattr(sls.functions, task.name, task.config)
            else:
                # TODO: log warning here
                pass

        for task in self.tasks:
            if not hasattr(sls.functions, task.name):
                setattr(sls.functions, task.name, task.config)
            else:
                # TODO: log warning here
                pass

        for feeder in self.feeders:
            if not hasattr(sls.functions, feeder.name):
                setattr(sls.functions, feeder.name, feeder.config)
            else:
                # TODO: log warning here
                pass

        # add all state machine step functions
        for workflow in self.workflows:
            if not hasattr(sls.stepFunctions.stateMachines, workflow.name):
                setattr(sls.stepFunctions.stateMachines, workflow.name, workflow.config)
            else:
                # TODO: log warning here
                pass

        # populate required plugin list
        try:
            sls.plugins.extend(SERVERLESS_PLUGINS)
        except AttributeError:
            sls.plugins = SERVERLESS_PLUGINS
        else:
            # deduplicate
            sls.plugins = list(set(sls.plugins))

        # include core and custom resource files
        sls.resources.Resources = sls.resources.get('Resources', {})
        for cr in core_resources():
            sls.resources.Resources.update(cr)

        bd = self.build_dir
        bd.mkdir(exist_ok=True)
        sls.to_file(bd.joinpath(DEFAULT_SERVERLESS_FILENAME))


project = Project()
