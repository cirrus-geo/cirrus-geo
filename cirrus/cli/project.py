import os
import sys
import json
import yaml

from typing import List, TypeVar
from pathlib import Path

from cirrus.cli.constants import (
    DEFAULT_BUILD_DIR_NAME,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_SERVERLESS_FILENAME,
    SERVERLESS_PLUGINS
)
from cirrus.cli.config import Config, DEFAULT_CONFIG_PATH
from cirrus.cli.exceptions import CirrusError
from cirrus.cli.utils import logging
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


C = TypeVar('C', bound='cirrus.cli.core.CoreTask')
F = TypeVar('F', bound='cirrus.cli.feeders.Feeder')
T = TypeVar('T', bound='cirrus.cli.tasks.Task')
W = TypeVar('W', bound='cirrus.cli.workflows.Workflow')


class Project:
    def __init__(self,
                 d: Path=None,
                 config: Config=None,
                 core_resources: List[NamedYamlable]=None,
                 core_tasks: List[F]=None,
                 feeders: List[F]=None,
                 tasks: List[T]=None,
                 workflows: List[W]=None,
                 ) -> None:
        self._config = config
        self._core_resources = core_resources
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
            raise CirrusError('Cirrus project path not set. Project is not initialized.')
        return self._path

    @property
    def path_safe(self) -> Path:
        from functools import cache
        if self._path is None:
            #logging.once(
            logger.warning(
                'No cirrus project specified; limited to built-in components/resources.',
            )
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
            self._config = Config.from_project(self)
        return self._config

    @property
    def core_resources(self) -> List[NamedYamlable]:
        if self._core_resources is None:
            from cirrus.cli.resources import core_resources
            self._core_resources = {}
            for resources in core_resources():
                for name, config in resources.items():
                    if name in self._core_resources:
                        logger.warning(
                            f"Duplicate resource declaration '{name}', overriding",
                        )
                    self._core_resources[name] = config
        return self._core_resources

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
        for dirname in ('feeders', 'tasks', 'workflows', 'resources'):
            d.joinpath(dirname).mkdir(exist_ok=True)

        def maybe_write_file(name, content):
            f = d.joinpath(name)
            if f.exists():
                logger.info(f'{name} already exists, skipping')
            else:
                f.write_text(content)

        maybe_write_file(DEFAULT_CONFIG_FILENAME, DEFAULT_CONFIG_PATH.read_text())
        maybe_write_file('package.json', json.dumps(
            {
                'name': 'cirrus',
                'version': '0.0.0',
                'description': '',
                'devDependencies': SERVERLESS_PLUGINS,
            },
            indent=2,
        ))

    def build(self) -> None:
        import shutil
        from cirrus.cli.utils import misc

        # get our cirrus-lib version to inject in each lambda
        cirrus_req = misc.get_cirrus_lib_requirement()

        # delete old build dir, and make it again
        bd = self.build_dir
        shutil.rmtree(bd)
        bd.mkdir()

        # write serverless config
        self.config.to_file(bd.joinpath(DEFAULT_SERVERLESS_FILENAME))

        # create and setup dirs for all lambdas
        fn_types = (self.feeders, self.tasks, self.core_tasks)
        for fns in fn_types:
            for fn in fns:
                fndir = bd.joinpath(fn.config.module)
                try:
                    fndir.mkdir(parents=True)
                except FileExistsError:
                    logger.debug(
                        f"Skipping linking lambda '{fn.name}': already exists",
                    )
                    continue

                for _file in fn.path.glob('*'):
                    if _file.name == fn.definition.filename:
                        logger.debug('Skipping linking definition file')
                        continue
                    # TODO: could have a problem on windows
                    # if lambda has a directory in it
                    fndir.joinpath(_file.name).symlink_to(_file)

                # write requirements file
                # TODO: make + work with YamlableList
                reqs = list(fn.python_requirements) + [cirrus_req]
                fndir.joinpath('requirements.txt').write_text(
                    '\n'.join(reqs),
                )


project = Project()
