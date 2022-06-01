#!/usr/bin/env python3
import sys

from pathlib import Path
from packaging.version import parse, Version


REDIRECT = '''<!DOCTYPE html>
<html>
  <head>
    <title>Redirecting to latest stable version docs</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url=./{}/index.html">
  </head>
</html>'''.format

INDEX = 'index.html'
STABLE_LINK_NAME = 'stable'
LATEST_LINK_NAME = 'dev'
LATEST_TARGET = 'main'


def main(gh_pages_dir):
    gh_pages_dir = Path(gh_pages_dir)

    all_versions = set()
    stable_version = parse('')
    for _file in gh_pages_dir.iterdir():
        if _file.is_dir():
            version = parse(_file.name)
            if not isinstance(version, Version):
                continue
            all_versions.add(str(version))
            if not version.is_prerelease and version > stable_version:
                stable_version = version

    stable_version = str(stable_version)

    # create 'stable' redirect to most-recent non-prerelease version
    stable = gh_pages_dir.joinpath(STABLE_LINK_NAME)
    stable.unlink(missing_ok=True)
    if stable_version:
        stable.symlink_to(stable_version)
        all_versions.add(STABLE_LINK_NAME)

    # create 'dev' redirect to main
    latest = gh_pages_dir.joinpath(LATEST_LINK_NAME)
    latest.unlink(missing_ok=True)
    latest.symlink_to(LATEST_TARGET)
    all_versions.add(LATEST_LINK_NAME)

    # write list of versions to versions file
    gh_pages_dir.joinpath('versions.txt').write_text('\n'.join(all_versions))

    # create index.html redirect
    index_version = stable_version if stable_version else LATEST_TARGET
    gh_pages_dir.joinpath(INDEX).write_text(REDIRECT(index_version))


if __name__ == '__main__':
    main(sys.argv[1])
