import os
import shutil
import tempfile

import pytest

from pathlib import Path

from cirrus.core.project import Project


@pytest.fixture(scope='module')
def fixture_data(pytestconfig):
    fdir = pytestconfig.rootpath.joinpath('tests', 'fixture_data')
    fdir.mkdir(exist_ok=True)
    return fdir


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
    return Project.resolve(strict=True)
