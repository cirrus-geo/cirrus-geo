import logging
import click
import textwrap

from typing import List
from pathlib import Path

from .. import files
from .component import Component
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class Lambda(Component):
    handler = files.PythonHandler()
    definition = files.LambdaDefinition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)

    def load_config(self):
        super().load_config()
        # we only support batch on tasks, but some things are
        # simpler if we know we are batch disabled for all Lambdas
        self.batch_enabled = False
        self.description = self.config.get('description', '')
        self.python_requirements = self.config.pop('python_requirements', [])

        self.lambda_config = self.config.get('lambda', NamedYamlable())
        self.lambda_enabled = self.lambda_config.pop('enabled', True) and self._enabled and bool(self.lambda_config)
        self.lambda_config.description = self.description
        self.lambda_config.environment = self.config.get('environment', {})

        if self.project and self.project.config:
            self.lambda_config.environment.update(self.project.config.provider.environment)

        self.lambda_config.package = {}
        self.lambda_config.package.include = []
        self.lambda_config.package.include.append(f'./lambdas/{self.name}/**')

        if not hasattr(self.lambda_config, 'module'):
            self.lambda_config.module = f'lambdas/{self.name}'
        if not hasattr(self.lambda_config, 'handler'):
            self.lambda_config.handler = 'lambda_function.lambda_handler'

    @property
    def enabled(self):
        return self._enabled and (self.lambda_enabled or self.batch_enabled)

    def display_attrs(self):
        if self.enabled and not self.lambda_enabled and not self.batch_enabled:
            yield 'DISABLED'
        yield from super().display_attrs()

    def detail_display(self):
        super().detail_display()
        click.echo(f'\nLambda enabled: {self.lambda_enabled}')
        if not self.lambda_config:
            return
        click.echo('Lambda config:')
        click.echo(textwrap.indent(self.lambda_config.to_yaml(), '  '))

    def get_outdir(self, project_build_dir: Path) -> Path:
        return project_build_dir.joinpath(self.lambda_config.module)

    def link_to_outdir(self, outdir: Path, project_python_requirements: List[str]) -> None:
        try:
            outdir.mkdir(parents=True)
        except FileExistsError:
            self.clean_outdir(outdir)

        for _file in self.path.iterdir():
            if _file.name == self.definition.name:
                logger.debug('Skipping linking definition file')
                continue
            # TODO: could have a problem on windows
            # if lambda has a directory in it
            # probably affects handler default too
            outdir.joinpath(_file.name).symlink_to(_file)

        reqs = self.python_requirements + project_python_requirements
        outdir.joinpath('requirements.txt').write_text(
            '\n'.join(reqs),
        )

    def clean_outdir(self, outdir: Path):
        try:
            contents = outdir.iterdir()
        except FileNotFoundError:
            return

        for _file in contents:
            _file.unlink()
