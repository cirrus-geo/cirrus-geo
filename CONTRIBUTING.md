# Contributing

## Project Setup

Get [uv](https://docs.astral.sh/uv/getting-started/installation/). Then:

```
git clone https://github.com/cirrus-geo/cirrus-geo.git
cd cirrus-geo
uv sync --group dev --extra cli --python <python_version>
```

Run pre-commit install to enable the pre-commit configuration:

```commandline
uv run pre-commit install
```

The pre-commit hooks will be run against all files during a `git commit`, or
you can run it explicitly with:

```commandline
uv run pre-commit run --all-files
```

If, for some reason, you wish to commit code that does not pass the
pre-commit checks, this can be done with:

```commandline
git commit -m "message" --no-verify
```

## Dependency management

Dependencies are defined in [`pyproject.toml`](./pyproject.toml):

* `[project.dependencies]`: base application dependencies
* `[project.optional-dependencies.cli]`: dependencies specific to the `cli` extra
* `[dependency-groups.dev]`: development dependencies
* `[dependency-groups.docs]`: dependencies for building docs

### Adding dependencies

To add a new base dependency:

```commandline
uv add <package_name>
```

To add a development dependency:

```commandline
uv add --group dev <package_name>
```

To add a documentation dependency:

```commandline
uv add --group docs <package_name>
```

To add a CLI-specific dependency:

```commandline
uv add --optional cli <package_name>
```

### Updating dependencies

To upgrade a specific package:

```commandline
uv sync --upgrade-package <package_name>
```

To upgrade all dependencies:

```commandline
uv sync --upgrade
```

### Installing all dependencies

To install all dependencies (base, dev, docs, and cli):

```commandline
uv sync --all-groups --all-extras
```
