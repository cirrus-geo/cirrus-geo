#!/usr/bin/env python3
import sys

from pathlib import Path

from packaging import version

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


class Version(version.Version):
    def __init__(self, version: str) -> None:
        super().__init__(version)
        self.name = version


def main(gh_pages_dir: Path | str) -> None:
    gh_pages_dir = Path(gh_pages_dir)

    all_versions: set[Version] = set()
    default_version = Version("0.0")
    stable_version = default_version
    links: set[str] = set()

    for _file in gh_pages_dir.iterdir():
        if _file.is_dir():
            try:
                _version = Version(_file.name)
            except version.InvalidVersion:
                continue
            all_versions.add(_version)
            if not _version.is_prerelease and _version > stable_version:
                stable_version = _version

    # create 'stable' redirect to most-recent non-prerelease version
    stable = gh_pages_dir.joinpath(STABLE_LINK_NAME)
    stable.unlink(missing_ok=True)
    if stable_version != default_version:
        stable.symlink_to(stable_version.name)
        links.add(STABLE_LINK_NAME)

    # create 'dev' redirect to main
    latest = gh_pages_dir.joinpath(LATEST_LINK_NAME)
    latest.unlink(missing_ok=True)
    latest.symlink_to(LATEST_TARGET)
    links.add(LATEST_LINK_NAME)

    # write sorted list of versions to versions file
    gh_pages_dir.joinpath("versions.txt").write_text(
        "\n".join(
            sorted(links) + [v.name for v in sorted(all_versions)],
        ),
    )

    # create index.html redirect
    index_version = stable_version.name if stable_version else LATEST_LINK_NAME
    gh_pages_dir.joinpath(INDEX).write_text(REDIRECT(index_version))


if __name__ == "__main__":
    main(sys.argv[1])
