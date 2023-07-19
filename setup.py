#!/usr/bin/env python
import os
import os.path
import subprocess

from setuptools import find_namespace_packages, setup

from src.cirrus.cli.constants import DESC

HERE = os.path.abspath(os.path.dirname(__file__))


# gets the version from the latest tag via git describe
# so we don't have to do anything to manage version number
# aside from tagging releases
def git_version(gitdir, default="0.0.0"):
    try:
        desc = subprocess.run(
            [
                "git",
                "--git-dir",
                gitdir,
                "describe",
                "--long",
                "--tags",
                "--dirty",
            ],
            capture_output=True,
        )
    except Exception:
        return default

    if desc.returncode != 0:
        return default

    # example output: v0.5.1-8-gb38722d-dirty
    # parts are:
    #  0 - last tag
    #  1 - commits since last tag (0 if same commit as tag)
    #  2 - short hash of current commit
    #  3 - dirty (if repo state is dirty)
    parts = desc.stdout.decode().strip().lstrip("v").split("-", maxsplit=2)
    if int(parts[1]) > 0 or "dirty" in parts[2]:
        return f'{parts[0]}+{parts[1]}.{parts[2].replace("-",".")}'
    else:
        return parts[0]


# in the case of a tagged release, we
# are passed a version in an env var
VERSION = os.environ.get(
    "CIRRUS_VERSION",
    git_version(os.path.join(HERE, ".git")),
)


with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
    readme = f.read()

with open(os.path.join(HERE, "requirements.txt"), encoding="utf-8") as f:
    reqs = f.read().split("\n")

install_requires = [x.strip() for x in reqs if "git+" not in x]
dependency_links = [x.strip().replace("git+", "") for x in reqs if "git+" not in x]


setup(
    name="cirrus-geo",
    python_requires=">=3.9",
    packages=find_namespace_packages("src"),
    package_dir={"": "src"},
    version=VERSION,
    description=DESC,
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Matthew Hanson (matthewhanson), Jarrett Keifer (jkeifer), Element 84",
    url="https://github.com/cirrus-geo/cirrus",
    install_requires=install_requires,
    dependency_links=dependency_links,
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    license="Apache-2.0",
    include_package_data=True,
    entry_points="""
        [console_scripts]
        cirrus=cirrus.cli.__main__:main
        [cirrus.resources]
        built-in=cirrus.builtins
    """,
)
