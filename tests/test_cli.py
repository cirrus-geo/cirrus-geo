import shlex
import shutil

import pytest

from click.testing import CliRunner

from cirrus.cli.commands import cli
from cirrus.cli.collections import make_collections
from cirrus.cli.project import Project


collections = make_collections()


@pytest.fixture(scope='session')
def cli_runner():
    return CliRunner(mix_stderr=False)


@pytest.fixture(scope='session')
def invoke(cli_runner):
    def _invoke(cmd, **kwargs):
        return cli_runner.invoke(cli, shlex.split(cmd), **kwargs)
    return _invoke


@pytest.fixture
def build_dir(module_tmpdir):
    return module_tmpdir.joinpath('.cirrus')


@pytest.fixture
def reference_build(fixture_data, build_dir):
    reference = fixture_data.joinpath('build')
    has_ref = reference.is_dir()
    # pass ref dir to test if we have one
    yield reference if has_ref else None
    # else we can copy test output to serve as reference
    if not has_ref:
        shutil.copytree(build_dir, reference)


def test_init(invoke, module_tmpdir):
    result = invoke('init')
    print(result.stdout, result.stderr)
    assert result.exit_code == 0
    assert Project.dir_is_project(module_tmpdir) is True


def test_reinit(module_tmpdir, invoke, project):
    result = invoke(f'init {project.path}')
    assert result.exit_code == 0


def test_build(invoke, project, reference_build, build_dir):
    import sys
    import filecmp
    import difflib
    result = invoke('build')
    print(result.stdout)
    print(result.stderr)
    print(result.exc_info)
    assert result.exit_code == 0
    assert build_dir.is_dir()

    if reference_build:
        dcmp = filecmp.dircmp(reference_build, build_dir)
        print(f'Files in missing from build: {dcmp.left_only}')
        print(f'Files added in build: {dcmp.right_only}')
        print(f'Files different in build: {dcmp.diff_files}')
        print(f'Files unable to be compared: {dcmp.funny_files}')
        for fname in dcmp.diff_files:
            with reference_build.joinpath(fname).open() as f1:
                with build_dir.joinpath(fname).open() as f2:
                    sys.stdout.writelines(difflib.unified_diff(
                        f1.readlines(),
                        f2.readlines(),
                        fromfile=f'expected {fname}',
                        tofile=f'generated {fname}',
                    ))

        assert not (dcmp.left_only or dcmp.right_only or dcmp.diff_files or dcmp.funny_files)


@pytest.mark.parametrize(
    'createable',
    [c.type for c in collections.extendable_collections
     if hasattr(c, 'add_create_command')],
)
def test_create(createable, module_tmpdir, invoke, project):
    result = invoke(f'create {createable} test_{createable} description')
    assert result.exit_code == 0
    result = invoke(f'show {createable} test_{createable}')
    assert result.exit_code == 0
    assert len(result.stdout) > 0


@pytest.mark.parametrize('collection', [c.collection_name for c in collections])
def test_show_list(collection, invoke):
    result = invoke(f'show {collection}')
    assert result.exit_code == 0
    assert len(result.stdout) > 0


@pytest.mark.parametrize('collection', [c.collection_name for c in collections])
def test_show_detail(collection, invoke):
    item = list(getattr(collections, collection).keys())[0]
    result = invoke(f'show {collection} {item}')
    assert result.exit_code == 0
    assert len(result.stdout) > 0
