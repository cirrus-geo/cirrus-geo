import os
import shutil

import pytest

from cirrus.core.project import Project

from . import plugin_testing


@pytest.fixture(scope='session')
def fixtures(pytestconfig):
    return  pytestconfig.rootpath.joinpath('tests', 'fixtures')


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


@pytest.fixture(scope='session', autouse=True)
def test_plugin(fixtures):
    dist = fixtures.joinpath('plugin', 'cirrus_test_plugin-0.0.0.dist-info')
    plugin_testing.add_plugin_finder(dist)
    yield
    plugin_testing.remove_plugin_finder(dist)
