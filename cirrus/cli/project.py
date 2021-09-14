import os
import sys
import json
import yaml

from pathlib import Path

from cirrus.cli.constants import (
    DEFAULT_BUILD_DIR_NAME,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_SERVERLESS_FILENAME,
    SERVERLESS,
    SERVERLESS_PLUGINS,
)
from cirrus.cli.config import Config, DEFAULT_CONFIG_PATH
from cirrus.cli.exceptions import CirrusError
from cirrus.cli.utils import logging
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class Project:
    def __init__(self, path: Path=None, config: Config=None) -> None:
        self._config = config
        self._serverless = None
        self._dynamic_attrs = [k[1:] for k in self.__dict__.keys() if k.startswith('_')]
        # do this after dynamic attrs
        # as we don't want it included
        self._path = None

        # set path not _path to use setter
        if path:
            self.path = path

        self.collections = []

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
    def build_dir(self) -> Path:
        return self.path.joinpath(DEFAULT_BUILD_DIR_NAME)

    @property
    def lambda_collections(self):
        from cirrus.cli.components.base import Lambda
        return [c for c in self.collections if issubclass(c.element_class, Lambda)]

    @property
    def stepfunction_collections(self):
        from cirrus.cli.components.base import StepFunction
        return [c for c in self.collections if issubclass(c.element_class, StepFunction)]

    @property
    def extendable_collections(self):
        return [c for c in self.collections if c.element_class.user_extendable]

    @property
    def resource_collections(self):
        from cirrus.cli.resources import Resource
        return [c for c in self.collections if issubclass(c.element_class, Resource)]

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

    def new(self, d: Path) -> None:
        for collection in self.extendable_collections:
            d.joinpath(collection.user_dir_name).mkdir(exist_ok=True)

        def maybe_write_file(name, content):
            f = d.joinpath(name)
            if f.exists():
                logger.info(f'{name} already exists, skipping')
            else:
                f.write_text(content)

        deps = SERVERLESS.copy()
        deps.update(SERVERLESS_PLUGINS)

        maybe_write_file(DEFAULT_CONFIG_FILENAME, DEFAULT_CONFIG_PATH.read_text())
        maybe_write_file('package.json', json.dumps(
            {
                'name': 'cirrus',
                'version': '0.0.0',
                'description': '',
                'devDependencies': deps,
            },
            indent=2,
        ))

    def build(self) -> None:
        import shutil
        from cirrus.cli.utils import misc

        # get our cirrus-lib version to inject in each lambda
        cirrus_req = [misc.get_cirrus_lib_requirement()]

        # make build dir or clean it up
        bd = self.build_dir
        try:
            bd.mkdir()
        except FileExistsError:
            pass

        # find existing lambda dirs, if any
        existing_dirs = set()
        for f in bd.iterdir():
            if not f.is_dir():
                continue
            if f.name == '.serverless':
                continue
            for d in f.iterdir():
                if not d.is_dir():
                    continue
                existing_dirs.add(d.resolve())

        # write serverless config
        self.config.to_file(bd.joinpath(DEFAULT_SERVERLESS_FILENAME))

        # setup all required lambda dirs
        fn_dirs = set()
        for collection in self.lambda_collections:
            for fn in collection.values():
                outdir = fn.get_outdir(bd).resolve()
                if outdir in fn_dirs:
                    logger.debug(
                        f"Duplicate function name '{fn.name}': skipping",
                    )
                    continue

                fn_dirs.add(outdir)
                fn.link_to_outdir(outdir, cirrus_req)

        # clean up existing but no longer used lambda dirs
        for d in existing_dirs - fn_dirs:
            shutil.rmtree(d)

    def clean(self) -> None:
        import shutil
        bd = self.build_dir
        if not bd.is_dir():
            return
        for f in self.build_dir.iterdir():
            if f.is_dir():
                shutil.rmtree(f)
            else:
                f.unlink()


project = Project()
