import shlex

from pathlib import Path

from cirrus import cli
from cirrus.project import Project


def test_init(tmpdir):
    cmd = shlex.split(f'init {tmpdir}')
    cli.main(cmd)
    Project.from_dir(Path(tmpdir))

def test_reinit(tmpdir):
    cmd = shlex.split(f'init {tmpdir}')
    cli.main(cmd)
    cli.main(cmd)
    Project.from_dir(Path(tmpdir))
