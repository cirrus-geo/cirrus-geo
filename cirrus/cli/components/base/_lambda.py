import logging
import click

from typing import List
from pathlib import Path

from .component import Component
from cirrus.cli.utils.yaml import NamedYamlable


logger = logging.getLogger(__name__)


class Lambda(Component):
    abstract = True

    def load_config(self):
        self.config = NamedYamlable.from_yaml(self.definition.content)
        self.description = self.config.get('description', '')
        self.python_requirements = self.config.pop('python_requirements', [])
        if not hasattr(self.config, 'module'):
            self.config.module = f'{self.plural_name}/{self.name}'
        if not hasattr(self.config, 'handler'):
            self.config.handler = f'{self.component_type}.handler'

    # TODO: not sure, but I think we should include the default
    # lambda files and have methods on the class to define the
    # content, which can be overriden as approprite by subclasses
    @property
    def definition(self):
        raise NotImplementedError("Must define a file named 'definition'")

    @click.command()
    def show(self):
        click.echo(self.files)

    def get_outdir(self, project_build_dir: Path) -> Path:
        return project_build_dir.joinpath(self.config.module)

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

        # write requirements file
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
