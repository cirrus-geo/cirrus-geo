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
        shutil.copytree(build_dir, reference, symlinks=True)


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
    assert result.exit_code == 0
    assert build_dir.is_dir()

    if reference_build:
        missing = []
        added = []
        changed = []
        failed = []

        # TODO: symlinks are not and cannot be easily compared
        def compare(dir1, dir2):
            nonlocal missing
            nonlocal added
            nonlocal changed
            nonlocal failed

            dcmp = filecmp.dircmp(dir1, dir2)
            missing += [dir1.joinpath(name) for name in dcmp.left_only]
            added += [dir2.joinpath(name) for name in dcmp.right_only]
            changed += [dir1.joinpath(name) for name in dcmp.diff_files]
            failed += [dir1.joinpath(name) for name in dcmp.funny_files]

            for subdir in dcmp.common_dirs:
                if not dir2.joinpath(subdir).is_symlink():
                    compare(dir1.joinpath(subdir), dir2.joinpath(subdir))

        compare(reference_build, build_dir)

        missing = [path.relative_to(reference_build) for path in missing]
        added = [path.relative_to(build_dir) for path in added]
        changed = [path.relative_to(reference_build) for path in changed]
        failed = [path.relative_to(reference_build) for path in failed]

        def print_list(msg, _list):
            print(msg)
            for item in _list:
                print(item)

        print_list('Files in missing from build:', missing)
        print_list('Files added in build: ', added)
        print_list('Files unable to be compared: ', failed)
        print_list('Files different in build: ', changed)
        print('Diff:')
        for fname in changed:
            with reference_build.joinpath(fname).open() as f1:
                with build_dir.joinpath(fname).open() as f2:
                    sys.stdout.writelines(difflib.unified_diff(
                        f1.readlines(),
                        f2.readlines(),
                        fromfile=f'expected {fname}',
                        tofile=f'generated {fname}',
                    ))

        assert not any((missing, added, changed, failed))


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
