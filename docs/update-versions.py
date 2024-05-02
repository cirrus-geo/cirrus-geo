#!/usr/bin/env python3
import sys

from pathlib import Path

from packaging.version import parse

REDIRECT = """<!DOCTYPE html>
<html>
  <head>
    <title>Redirecting to latest stable version docs</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url=./{}/index.html">
  </head>
</html>""".format

INDEX = "index.html"
STABLE_LINK_NAME = "stable"
LATEST_LINK_NAME = "dev"
LATEST_TARGET = "main"


def main(gh_pages_dir):
    gh_pages_dir = Path(gh_pages_dir)

    all_versions = set()
    default_version = parse("0.0")
    stable_version = default_version
    for _file in gh_pages_dir.iterdir():
        if _file.is_dir():
            try:
                version = parse(_file.name)
            except Exception:
                continue
            version.name = _file.name
            all_versions.add(version.name)
            if not version.is_prerelease and version > stable_version:
                stable_version = version

    stable_version = stable_version.name

    # create 'stable' redirect to most-recent non-prerelease version
    stable = gh_pages_dir.joinpath(STABLE_LINK_NAME)
    stable.unlink(missing_ok=True)
    if stable_version != default_version:
        stable.symlink_to(stable_version)
        all_versions.add(STABLE_LINK_NAME)

    # create 'dev' redirect to main
    latest = gh_pages_dir.joinpath(LATEST_LINK_NAME)
    latest.unlink(missing_ok=True)
    latest.symlink_to(LATEST_TARGET)
    all_versions.add(LATEST_LINK_NAME)

    # write list of versions to versions file
    gh_pages_dir.joinpath("versions.txt").write_text("\n".join(all_versions))

    # create index.html redirect
    index_version = stable_version if stable_version else LATEST_LINK_NAME
    gh_pages_dir.joinpath(INDEX).write_text(REDIRECT(index_version))


if __name__ == "__main__":
    main(sys.argv[1])
