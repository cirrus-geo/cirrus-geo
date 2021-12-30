import os
import os.path

from typing import List
from pathlib import Path


def get_cirrus_lib_requirements() -> List[str]:
    '''
    Get the cirrus-lib dependencies.
    '''
    try:
        from importlib import metadata
    except ImportError:
        import importlib_metadata as metadata

    return [
        req.split(';')[0].translate(str.maketrans('','',' ()'))
        for req in metadata.requires('cirrus-lib')
    ]


def relative_to(path1: Path, path2: Path) -> Path:
    common_path = path1
    relative = ''
    path = path2.resolve()
    result = path

    while True:
        try:
            result = path.relative_to(common_path)
        except ValueError:
            _common_path = common_path.parent
            relative += '../'
        else:
            if not relative:
                relative = './'
            return Path(relative + str(result))

        if _common_path == common_path:
            break

        common_path = _common_path

    return result


def relative_to_cwd(path: Path) -> Path:
    return '.{}{}'.format(
        os.path.sep,
        relative_to(Path(os.getcwd()), path),
    )
