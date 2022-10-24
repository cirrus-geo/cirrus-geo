# Contributing

## Project Setup

Configure your virtual environment of choice with Python 3.7 through 3.10. Python 3.9 is recommended.

Install pip requirements and local code with:

```commandline
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

Run pre-commit install to enable the pre-commit configuration:

```commandline
pre-commit install
```

The pre-commit hooks will be run against all files during a `git commit`, or you can run it explicitly with:

```commandline
pre-commit run --all-files
```

If for some reason, you wish to commit code that does not pass the precommit checks, this can be done with:

```commandline
git commit -m "message" --no-verify
```
