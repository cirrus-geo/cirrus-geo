import os
import shlex

import pytest
from functools import partial

from click.testing import CliRunner

from cirrus.cli.commands import cli
from cirrus.cli.project import Project, project


@pytest.fixture(scope='session')
def cli_runner():
    return CliRunner(mix_stderr=False)


@pytest.fixture(scope='session')
def invoke(cli_runner):
    def _invoke(cmd, **kwargs):
        return cli_runner.invoke(cli, shlex.split(cmd), **kwargs)
    return _invoke


def test_init(invoke, module_tmpdir):
    result = invoke('init')
    assert result.exit_code == 0
    assert Project.dir_is_project(module_tmpdir) == True


def test_reinit(module_tmpdir, invoke, project):
    result = invoke(f'init {project.path}')
    assert result.exit_code == 0


@pytest.mark.parametrize(
    'createable',
    [c.element_class.name for c in project.extendable_collections
     if hasattr(c.element_class, 'add_create_command')],
)
def test_create(createable, module_tmpdir, invoke, project):
    result = invoke(f'create {createable} test_{createable}')
    assert result.exit_code == 0
    result = invoke(f'show {createable} test_{createable}')
    assert result.exit_code == 0
    assert len(result.stdout) > 0
