import os
import shutil
from pathlib import Path

import pytest

from cirrus.core.project import Project

from . import plugin_testing


@pytest.fixture(scope="session")
def fixtures():
    return Path(__file__).parent.joinpath("fixtures")


@pytest.fixture(scope="module")
def project_testdir():
    pdir = Path(__file__).parent.joinpath("output")
    if pdir.is_dir():
        shutil.rmtree(pdir)
    pdir.mkdir()
    old_cwd = os.getcwd()
    os.chdir(pdir)
    yield pdir
    os.chdir(old_cwd)


@pytest.fixture
def project(project_testdir):
    return Project.resolve(strict=True)


@pytest.fixture(scope="module", autouse=True)
def test_plugin(fixtures):
    dist = fixtures.joinpath("plugin", "cirrus_test_plugin-0.0.0.dist-info")
    plugin_testing.add_plugin_finder(dist)
    yield
    plugin_testing.remove_plugin_finder(dist)
