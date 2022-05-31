import os
import os.path
import shlex
import hashlib
import json

import pytest

from click.testing import CliRunner
from pathlib import Path

from cirrus.cli.commands import cli
from cirrus.core.groups import make_groups
from cirrus.core.project import Project


groups = make_groups()


def shasum(path: Path):
    blocksize = 2**18
    sha = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            data = f.read(blocksize)
            if not data:
                break
            sha.update(data)
    return sha.hexdigest()


def hash_tree(src_dir):
    hashed = {}
    for root, dirs, files in os.walk(src_dir):
        root = Path(root)
        for f in files:
            if f.startswith('.'):
                continue
            f = root.joinpath(f)
            hashed[str(f.relative_to(src_dir))] = {
                'shasum': shasum(f),
                'size': f.stat().st_size,
            }
    return hashed


@pytest.fixture(scope='session')
def cli_runner():
    return CliRunner(mix_stderr=False)


@pytest.fixture(scope='session')
def invoke(cli_runner):
    def _invoke(cmd, **kwargs):
        return cli_runner.invoke(cli, shlex.split(cmd), **kwargs)
    return _invoke


@pytest.fixture
def build_dir(project_testdir):
    return project_testdir.joinpath('.cirrus')


@pytest.fixture
def reference_build(fixture_data, build_dir):
    reference = fixture_data.joinpath('build')
    has_ref = reference.is_dir()
    # pass ref dir to test if we have one
    yield reference if has_ref else None
    # else we can copy test output to serve as reference
    if not has_ref:
        reference.mkdir()
        with reference.joinpath('hashes.json').open('w') as f:
            json.dump(hash_tree(build_dir), f, indent=4)
        reference.joinpath('serverless.yml').write_bytes(
            build_dir.joinpath('serverless.yml').read_bytes(),
        )


def test_init(invoke, project_testdir):
    result = invoke('init')
    print(result.stdout, result.stderr)
    assert result.exit_code == 0
    assert Project.dir_is_project(project_testdir) is True


def test_reinit(project_testdir, invoke, project):
    result = invoke(f'init {project.path}')
    assert result.exit_code == 0


def test_build(invoke, project, reference_build, build_dir):
    import sys
    import difflib
    result = invoke('build')
    print(result.stdout)
    print(result.stderr)
    print(result.exc_info)
    assert result.exit_code == 0
    assert build_dir.is_dir()

    if reference_build:
        with reference_build.joinpath('hashes.json').open() as f:
            old_hashes = json.load(f)
        new_hashes = hash_tree(build_dir)
        old_keys = old_hashes.keys()
        new_keys = new_hashes.keys()

        missing = list(old_keys - new_keys)
        added = list(new_keys - old_keys)
        changed = [
            k for k in old_keys & new_keys
            if old_hashes[k] != new_hashes[k]
        ]

        print(f'Files in missing from build: {missing}')
        print(f'Files added in build: {added}')
        print(f'Files different in build: {changed}')

        # we diff serverless as that is the most complicated
        if 'serverless.yml' in changed:
            with reference_build.joinpath('serverless.yml').open() as f1:
                with build_dir.joinpath('serverless.yml').open() as f2:
                    sys.stdout.writelines(difflib.unified_diff(
                        f1.readlines(),
                        f2.readlines(),
                        fromfile='expected serverless.yml',
                        tofile='generated serverless.yml',
                    ))

        print(
            '\n'
            f'Reference build: {reference_build}\n'
            f'Test build directory: {build_dir}\n'
            '\n'
            'If all highlighted changes are expected, simply remove \n'
            'the reference_build directory and rerun the tests to update \n'
            'the reference files.'
        )

        assert not (missing or added or changed)


@pytest.mark.parametrize(
    'createable',
    [c.type for c in groups.extendable_groups
     if hasattr(c, 'add_create_command')],
)
def test_create(createable, project_testdir, invoke, project):
    result = invoke(f'create {createable} test_{createable} description')
    assert result.exit_code == 0
    result = invoke(f'show {createable} test_{createable}')
    assert result.exit_code == 0
    assert len(result.stdout) > 0


@pytest.mark.parametrize('group', [c.group_name for c in groups])
def test_show_list(group, invoke):
    result = invoke(f'show {group}')
    assert result.exit_code == 0
    assert len(result.stdout) > 0


def test_show_plugins(invoke):
    result = invoke(f'show plugins')
    assert result.exit_code == 0


@pytest.mark.parametrize('group', [c.group_name for c in groups])
def test_show_detail(group, invoke):
    item = next(iter(getattr(groups, group))).name
    result = invoke(f'show {group} {item}')
    assert result.exit_code == 0
    assert len(result.stdout) > 0
