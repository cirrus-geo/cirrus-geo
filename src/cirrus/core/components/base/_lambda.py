import logging
import click
import textwrap
import copy

from pathlib import Path

from .. import files
from .component import Component
from cirrus.core.utils.yaml import NamedYamlable


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
        self.environment = self.config.get('environment', NamedYamlable())

        self.lambda_config = self.config.get('lambda', NamedYamlable())
        self.lambda_enabled = self.lambda_config.pop('enabled', True) and self._enabled and bool(self.lambda_config)
        self.lambda_config.description = self.description

        project_reqs = []
        if self.project and self.project.config:
            project_reqs = list(
                self.project.config.custom.pythonRequirements.include
            )
            # update task env with defaults from project config
            self.environment = (
                self.project.config.provider.environment | self.environment
            )

        # update lambda env with the merged project/task env
        self.lambda_config.environment = (
            self.environment | self.lambda_config.get('environment', {})
        )

        self.lambda_config.package = {}
        self.lambda_config.package.include = []
        self.lambda_config.package.include.append(f'./lambdas/{self.name}/**')

        if not hasattr(self.lambda_config, 'pythonRequirements'):
            self.lambda_config.pythonRequirements = {}
        # note the set to deduplicate requirements
        # TODO: multiple versions of the same requirement
        # will not be deduplicated
        self.lambda_config.pythonRequirements['include'] = sorted(list({
            req for req in
            # list of all requirements specified in lambda config
            # and the global pythonRequiments from cirrus.yml
            self.lambda_config.pythonRequirements.get('include', [])
            + project_reqs
        }))

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

    def copy_for_config(self):
        '''any modifications to config for serverless.yml go here'''
        lc = copy.deepcopy(self.lambda_config)
        lc.pop('pythonRequirements', None)
        return lc

    def get_outdir(self, project_build_dir: Path) -> Path:
        return project_build_dir.joinpath(self.lambda_config.module)

    def copy_to_outdir(self, outdir: Path) -> None:
        import shutil

        try:
            outdir.mkdir(parents=True)
        except FileExistsError:
            self.clean_outdir(outdir)

        for _file in self.path.iterdir():
            if _file.name == self.definition.name:
                logger.debug('Skipping linking definition file')
                continue
            if _file.is_dir():
                shutil.copytree(
                    _file,
                    outdir.joinpath(_file.name),
                    ignore=shutil.ignore_patterns('*.pyc', '__pycache__'),
                )
            else:
                shutil.copyfile(_file, outdir.joinpath(_file.name))

        outdir.joinpath('requirements.txt').write_text(
            ''.join(
                [f'{req}\n' for req in
                 self.lambda_config.pythonRequirements.get('include', [])],
            ),
        )

    def clean_outdir(self, outdir: Path):
        try:
            contents = outdir.iterdir()
        except FileNotFoundError:
            return

        for _file in contents:
            _file.unlink()
