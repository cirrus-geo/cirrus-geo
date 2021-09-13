import os
import shlex

from click.testing import CliRunner
from pathlib import Path

from cirrus.cli.commands import cli
from cirrus.cli.project import Project


def test_init(tmpdir):
    os.chdir(tmpdir)
    runner = CliRunner()
    result = runner.invoke(cli, 'init')
    print(result.stdout)
    print(os.system('pwd'))
    print(os.system('ls -l'))
    assert result.exit_code == 0
    Project(Path(tmpdir))
    Project.config


def test_reinit(tmpdir):
    runner = CliRunner()
    cmd = shlex.split(f'init {tmpdir}')
    result = runner.invoke(cli, cmd)
    assert result.exit_code == 0
    result = runner.invoke(cli, cmd)
    assert result.exit_code == 0
    Project(Path(tmpdir))
    Project.config
