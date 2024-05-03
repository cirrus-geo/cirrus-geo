# Contributing

## Project Setup

Configure your virtual environment. Check the
[`pyproject.toml`](./pyproject.toml) file for the required python version.

Install pip requirements and local code with:

```commandline
pip install -r requirements-dev.txt
pip install -c requirements.txt -e '.[cli]'
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

Dependencies of the application itself are defined in the
[`pyproject.toml`](./pyproject.toml) file. Development and docs build
dependencies are defined in the [`requirements-dev.in`](./requirements-dev.in)
and [`requirements-docs.in`](./requirements-docs.in) files, respectively.
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
