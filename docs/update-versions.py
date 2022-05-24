#!/usr/bin/env python3
import sys

from pathlib import Path
from packaging.version import Version, parse


def main(gh_pages_dir):
    gh_pages_dir = Path(gh_pages_dir)

    all_versions = []
    latest_stable = Version('0.0.0')
    for f in gh_pages_dir.iterdir():
        if f.is_dir():
           all_versions.append(f.name)
           v = parse(f.name)
           if not v.is_prerelease and v > latest_stable:
               latest_stable = v

    # create symlink 'stable' pointing to
    # most-recent non-prerelease version
    stable = gh_pages_dir.joinpath('stable')
    if stable.is_symlink():
        stable.unlink()
    gh_pages_dir.joinpath('stable').symlink_to(str(latest_stable))

    # write list of versions to versions file
    gh_pages_dir.joinpath('versions.txt').write_text('\n'.join(all_versions))


if __name__ == '__main__':
    main(sys.argv[1])
