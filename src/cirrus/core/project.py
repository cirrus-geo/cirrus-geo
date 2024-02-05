import json
import logging
import os
from pathlib import Path

from cirrus.core.config import DEFAULT_CONFIG_PATH, Config
from cirrus.core.constants import (
    DEFAULT_BUILD_DIR_NAME,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_DOT_DIR_NAME,
    DEFAULT_GIT_IGNORE,
    DEFAULT_SERVERLESS_FILENAME,
    SERVERLESS,
    SERVERLESS_PLUGINS,
)
from cirrus.core.exceptions import CirrusError
from cirrus.core.groups import make_groups

logger = logging.getLogger(__name__)


class Project:
    def __init__(self, path: Path, config: Config = None) -> None:
        if path is not None and not self.dir_is_project(path):
            raise CirrusError(
                f"Cannot set project path, does not appear to be vaild project: '{path}'",
            )
        self.path = path
        self.config = config or self.load_config()
        self.groups = make_groups(project=self)
        self._dot_dir = None
        self._build_dir = None

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.path}>"

    def load_config(self) -> Config:
        if self.path is None:
            logger.debug(
                "Project path unset, cannot load configuration",
            )
            return None
        return Config.from_project(self)

    @property
    def dot_dir(self) -> Path:
        if self.path is None:
            return None
        if self._dot_dir is None:
            self._dot_dir = self.path.joinpath(DEFAULT_DOT_DIR_NAME)
            self._dot_dir.mkdir(exist_ok=True)
        return self._dot_dir

    @property
    def build_dir(self) -> Path:
        if self.dot_dir is None:
            return None
        if self._build_dir is None:
            self._build_dir = self.dot_dir.joinpath(DEFAULT_BUILD_DIR_NAME)
            self._build_dir.mkdir(exist_ok=True)
        return self._build_dir

    @classmethod
    def resolve(cls, path: Path = None, strict=False):
        if path is None:
            path = Path(os.getcwd())
        else:
            path = path.resolve()

        project_path = None

        def dirs(path):
            yield path
            yield from path.parents

        for parent in dirs(path):
            if Project.dir_is_project(parent):
                project_path = parent
                break

        if strict and project_path is None:
            raise CirrusError(
                "Unable to resolve project path and 'strict' resolution specified"
            )

        return cls(project_path)

    @staticmethod
    def dir_is_project(path: Path) -> bool:
        config = path.joinpath(DEFAULT_CONFIG_FILENAME)
        return config.is_file()

    @classmethod
    def new(cls, path: Path) -> None:
        def maybe_write_file(name, content):
            f = path.joinpath(name)
            if f.exists():
                logger.info(f"{name} already exists, skipping")
            else:
                f.write_text(content)

        deps = SERVERLESS.copy()
        deps.update(SERVERLESS_PLUGINS)

        maybe_write_file(DEFAULT_CONFIG_FILENAME, DEFAULT_CONFIG_PATH.read_text())
        maybe_write_file(
            "package.json",
            json.dumps(
                {
                    "name": "cirrus",
                    "version": "0.0.0",
                    "description": "",
                    "devDependencies": deps,
                },
                indent=2,
            ),
        )
        maybe_write_file(".gitignore", DEFAULT_GIT_IGNORE)

        self = cls(path)
        self.groups.ensure_created()

        return self

    def build(self) -> None:
        if self.path is None:
            raise CirrusError("Cannot build a project without the path set")

        import shutil

        import cirrus.lib2
        from cirrus.core.utils import misc

        # make build dir or clean it up
        bd = self.build_dir
        try:
            bd.mkdir()
        except FileExistsError:
            pass

        try:
            shutil.rmtree(bd.joinpath("cirrus"))
        except FileNotFoundError:
            pass

        # find existing lambda dirs, if any
        existing_dirs = set()
        for f in bd.iterdir():
            if not f.is_dir():
                continue
            if f.name in [".serverless"]:
                continue
            for d in f.iterdir():
                if d.is_symlink() or not d.is_dir():
                    continue
                existing_dirs.add(d.resolve())

        # write serverless config
        self.config.build(self.groups).to_file(
            bd.joinpath(DEFAULT_SERVERLESS_FILENAME),
        )

        # copy built-in lib2 to build dir for packaging
        # this is temporary until we can come up with a better
        # mechanism that:
        #
        #   1) removes the strict cirrus-geo dependency on cirrus-lib
        #   2) converts all built-ins to using the built-in lib functions
        #   3) provides a way for project lambda to get the desired cirrus-lib
        #
        # I think the solution for #3 is to use the python requirements
        # plugin with cirrus-lib as a requirement, where a dependency.
        # Built-ins using the built-in lib would still need the dependency
        # injection used here for lib2, but I'm imagining a special-case
        # way to handle this used internally only should be possible.
        #
        # Note that one motivation to having a single cirrus-lib version
        # initially was the ability to update project dependencies without
        # having to touch every single lambda. I believe this need is mitigated
        # by the fact that projects now maintain fewer lambdas than prior to
        # the project structure/cirrus cli revamp.
        lib_dir = bd.joinpath("cirrus", "lib2")
        shutil.copytree(
            cirrus.lib2.__path__[0],
            lib_dir,
            ignore=shutil.ignore_patterns("*.pyc", "__pycache__"),
        )

        # setup all required lambda dirs
        fn_dirs = set()
        for fn in self.groups.lambdas:
            outdir = fn.get_outdir(bd)

            if not outdir:
                continue

            outdir = fn.get_outdir(bd).resolve()
            if outdir in fn_dirs:
                logger.debug(
                    f"Duplicate function name '{fn.name}': skipping",
                )
                continue

            # create lambda dir
            fn_dirs.add(outdir)
            # copy contents
            fn.copy_to_outdir(outdir)
            # link in cirrus-lib
            outdir.joinpath("cirrus").symlink_to(
                misc.relative_to(outdir, lib_dir.parent),
            )

        # clean up existing but no longer used lambda dirs
        for d in existing_dirs - fn_dirs:
            shutil.rmtree(d)

    def clean(self, directory) -> None:
        if self.path is None:
            raise CirrusError("Cannot clean a project without the path set")

        try:
            directory.relative_to(self.dot_dir)
        except ValueError:
            raise ValueError(
                f"Directory must be child of cirrus dot dir: {directory}, {self.dot_dir}",
            ) from None

        from cirrus.core.utils.misc import clean_dir

        clean_dir(directory)
