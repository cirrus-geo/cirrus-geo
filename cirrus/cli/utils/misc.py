import os
from pathlib import Path


def get_cirrus_lib_requirement() -> str:
    '''
    Get the cirrus-lib dependency specified for this package.
    '''
    try:
        from importlib import metadata
    except ImportError:
        import importlib_metadata as metadata

    package_name = 'cirrus-geo'
    return [
        req for req in metadata.requires(package_name)
        if req.startswith('cirrus-lib')
    ][0]


def relative_to_cwd(path: Path) -> Path:
    common_path = Path(os.getcwd())
    relative = ''
    path = path.resolve()
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
