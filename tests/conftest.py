import os
import shutil
import tempfile

import pytest

from pathlib import Path

from cirrus.cli.project import Project

# same initialization we get when we run the cli
# TODO: it seems like this should happen when we import project...
#       that import seems like the hook into the loading we expect
#       maybe splitting Project from project would help where we _don't_ want to load
from cirrus.cli import __main__


@pytest.fixture(scope='module')
def module_tmpdir():
    old_cwd = os.getcwd()
    newpath = tempfile.mkdtemp()
    os.chdir(newpath)
    yield Path(newpath)
    os.chdir(old_cwd)
    shutil.rmtree(newpath)


@pytest.fixture
def project():
    project = Project()
    project.resolve(path=Path(os.getcwd()))
    print(project.path)
    return project
