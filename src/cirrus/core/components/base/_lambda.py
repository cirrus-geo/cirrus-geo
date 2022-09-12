import logging
import click
import textwrap
import copy

from pathlib import Path
from pkg_resources import Requirement

from cirrus.core.exceptions import DuplicateRequirement
from cirrus.core.components import files
from cirrus.core.components.base import Component
from cirrus.core.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class Lambda(Component):
    handler = files.PythonHandler()
    definition = files.LambdaDefinition()
    # TODO: Readme should be required once we have one per task
    readme = files.Readme(optional=True)
    user_extendable = False

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
        # note the set to deduplicate requirements but that different
        # versions/pinning for the same package will not be deduplicated
        self.lambda_config.pythonRequirements['include'] = sorted(list({
            req for req in
            # list of all requirements specified in lambda config
            # and the global pythonRequiments from cirrus.yml
            self.lambda_config.pythonRequirements.get('include', [])
            + project_reqs
        }))

        if hasattr(self.lambda_config, 'handler'):
            # this is a non-container lambda that needs to be packaged
            # by serverless, then we need to ensure the module points to the
            # place in the build dir where we'll copy all the code
            self.lambda_config.module = f'lambdas/{self.name}'
        elif not hasattr(self.lambda_config, 'image'):
            # this is also not a container lambda, which means it is likely
            # a lambda that has not been updated to have an explicit handler
            raise ValueError(
                'Missing module parameter in lambda definiton.yml. '
                'The handler parameter, which sets the module, is no longer defaulted. '
                'You likely need to set it to be like:\n\n'
                '    lambda:\n      handler: lambda_function.lambda_handler\n\n'
                f'Offending {self.type}: {self.name}\n\n'
                'See https://github.com/cirrus-geo/cirrus-geo/issues/139 for additional context.'
            ) from None


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
        if not self.lambda_enabled or not hasattr(self.lambda_config, 'module'):
            return None
        return project_build_dir.joinpath(self.lambda_config.module)

    def copy_to_outdir(self, outdir: Path) -> None:
        import shutil

        if not self.lambda_enabled:
            return

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

        requirements = self.lambda_config.pythonRequirements.get('include', [])
        requirements_str = '\n'.join(requirements)

        # if we have multiple versions specified for the same requirement
        # we want to throw a meaningful error, so we parse them all here
        # and check for dups
        req_names = set()
        for req in requirements:
            req = Requirement.parse(req)
            if req.name in req_names:
                raise DuplicateRequirement(
                    f"ERROR: Duplicated requirement for {self.type} '{self.name}', package '{req.name}'.\n\n"
                    'At this time cirrus does not support verison conflict resolution.\n'
                    'Please review the requirements keeping in mind those for cirrus-lib.\n'
                    'See https://github.com/cirrus-geo/cirrus-geo/issues/106 for context.\n\n'
                    f'Full requirements list:\n{requirements_str}'
                )
            else:
                req_names.add(req.name)

        outdir.joinpath('requirements.txt').write_text(requirements_str + '\n')

    def clean_outdir(self, outdir: Path):
        import shutil
        try:
            contents = outdir.iterdir()
        except FileNotFoundError:
            return

        for _file in contents:
            if not _file.is_symlink() and _file.is_dir():
                shutil.rmtree(_file)
            else:
                _file.unlink()
