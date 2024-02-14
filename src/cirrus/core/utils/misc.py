import os
import os.path
from importlib import metadata
from pathlib import Path


def get_cirrus_geo_requirements() -> list[str]:
    """
    Get the cirrus-geo dependencies.
    """
    return [
        req.split(";")[0].translate(str.maketrans("", "", " ()"))
        for req in metadata.requires("cirrus-geo")
    ]


def relative_to(path1: Path, path2: Path) -> Path:
    # differs from Path.relative_to(), as this impl
    # figures out how to get between to paths relatively
    # in cases that path method doesn't handle
    common_path = path1
    relative = ""
    path = path2.resolve()
    result = path

    while True:
        try:
            result = path.relative_to(common_path)
        except ValueError:
            _common_path = common_path.parent
            relative += "../"
        else:
            if not relative:
                relative = "./"
            return Path(relative + str(result))

        if _common_path == common_path:
            break

        common_path = _common_path

    return result


def relative_to_cwd(path: Path) -> Path:
    return ".{}{}".format(
        os.path.sep,
        relative_to(Path(os.getcwd()), path),
    )


def clean_dir(directory: Path) -> None:
    import shutil

    if not directory.is_dir():
        return

    for f in directory.iterdir():
        if not f.is_symlink() and f.is_dir():
            shutil.rmtree(f)
        else:
            f.unlink()


def import_path(name, path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    spec.loader = importlib.util.LazyLoader(spec.loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
