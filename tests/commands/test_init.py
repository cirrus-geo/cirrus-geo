import os
import shlex

from click.testing import CliRunner
from pathlib import Path

from cirrus import cli
from cirrus.project import Project


def test_init(tmpdir):
    os.chdir(tmpdir)
    runner = CliRunner()
    result = runner.invoke(cli.main, 'init')
    print(result.stdout)
    print(os.system('pwd'))
    print(os.system('ls -l'))
    assert result.exit_code == 0
    Project.from_dir(Path(tmpdir))


def test_reinit(tmpdir):
    runner = CliRunner()
    cmd = shlex.split(f'init {tmpdir}')
    result = runner.invoke(cli.main, cmd)
    assert result.exit_code == 0
    result = runner.invoke(cli.main, cmd)
    assert result.exit_code == 0
    Project.from_dir(Path(tmpdir))
