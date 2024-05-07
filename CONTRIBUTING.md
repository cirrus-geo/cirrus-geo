# Contributing

## Project Setup

Configure your virtual environment. Check the
[`pyproject.toml`](./pyproject.toml) file for the required python version.

Install pip requirements and local code with:

```commandline
pip install -r requirements-dev.txt
pip install -e '.[cli]'
```

Run pre-commit install to enable the pre-commit configuration:

```commandline
pre-commit install
```

The pre-commit hooks will be run against all files during a `git commit`, or
you can run it explicitly with:

```commandline
pre-commit run --all-files
```

If for some reason, you wish to commit code that does not pass the precommit
checks, this can be done with:

```commandline
git commit -m "message" --no-verify
```

## Dependency management

Dependencies are defined in `./requirements-in/*.in`:

* [`./requirements-in/10_requirements.in`](./requirements-in/10_requirements.in):
  base application dependencies
* [`./requirements-in/20_requirements-cli.in`](./requirements-in/20_requirements-cli.in):
  dependencies specific to the `cli` extra
* [`./requirements-in/40_requirements-dev.in`](./requirements-in/40_requirements-dev.in):
  developement dependencies
* [`./requirements-in/40_requirements-dev.in`](./requirements-in/50_requirements-docs.in):
  dependencies for building docs

`pip-compile` is used to take the different requirements sources and compile
them into `.txt` files for use with `pip`.

To simplify dependency updates, the script
[`./bin/compile-requirements.bash`](./bin/compile-requirements.bash) is
provided to automate running `pip-compile` for each of these dependency
sources. To use it, just run it like this:

```commandline
./bin/compile-requirements.bash
```

It will pass any arguments through to the underlying `pip-compile` calls. For
example, upgrading a package looks like this:

```commandline
./bin/compile-requirements.bash --upgrade-package <package_name>
```

To upgrade all dependencies:

```commandline
./bin/compile-requirements.bash --upgrade
```

Because the `*.in` files have dependencies on one another (to ensure we are
pinning shared transitive dependencies in a compatible way we use previous
`*.txt` files as constraints as necessary), the `*.in` files are prefixed with
a number. This number expresses the dependency relationship such that sorting
the files by name will also enforce the dependency ordering.
