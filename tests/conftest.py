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
def project_testdir(pytestconfig):
    pdir = pytestconfig.rootpath.joinpath('tests', 'output')
    if pdir.is_dir():
        shutil.rmtree(pdir)
    pdir.mkdir()
    old_cwd = os.getcwd()
    os.chdir(pdir)
    yield pdir
    os.chdir(old_cwd)


@pytest.fixture
def project():
    return Project.resolve(strict=True)
