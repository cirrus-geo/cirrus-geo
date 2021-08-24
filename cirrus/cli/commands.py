import click

from pathlib import Path
from cirrus.cli import constants
from cirrus.cli.project import project
from cirrus.cli.utils import (
    logging,
    click as utils_click,
)


logger = logging.getLogger(__name__)


@click.group(
    name=constants.PROG,
    help=constants.DESC,
    cls=utils_click.AliasedShortMatchGroup,
)
@click.option(
    '--cirrus-dir',
    envvar='CIRRUS_DIR',
    type=click.Path(
        exists=True,
        file_okay=False,
        resolve_path=True,
        path_type=Path,
    ),

)
@logging.verbosity()
def cli(verbose, cirrus_dir=None):
    if cirrus_dir:
        project.set_path(cirrus_dir)
    else:
        project.resolve()


@cli.command()
@click.argument(
    'directory',
    required=False,
    default=None,
    type=click.Path(
        exists=True,
        file_okay=False,
        writable=True,
        resolve_path=True,
        path_type=Path,
    ),
)
def init(directory=None):
    '''
    Initialize a cirrus project in DIRECTORY.

    DIRECTORY defaults to the current working directory.
    '''
    if not directory:
        directory = Path.cwd()
    project.new(directory)
    click.secho(
        f"Succesfully initialized project in '{directory}'.",
        err=True,
        fg='green',
    )


@cli.command()
@utils_click.requires_project
def build():
    '''
    Build the cirrus configuration into a serverless.yml.
    '''
    project.build()


@cli.command()
@utils_click.requires_project
def clean():
    '''
    Remove all files from the cirrus build directory.
    '''
    project.clean()


@cli.command(
    aliases=['sls'],
    context_settings=dict(
        ignore_unknown_options=True,
    ),
)
@click.argument('sls_args', nargs=-1, type=click.UNPROCESSED)
@utils_click.requires_project
def serverless(sls_args):
    '''
    Run serverless within the cirrus build directory.
    '''
    import os

    bd = project.build_dir
    if not bd.is_dir():
        logger.error('No build directory; have you run a build?')
        return

    sls = project.path.joinpath('node_modules', 'serverless', 'bin', 'serverless.js')
    if not sls.is_file():
        logger.error('No serverless binary; have you run `npm install`?')
        return

    os.chdir(bd)
    os.execv(sls, ['serverless'] + list(sls_args))


@cli.group(cls=utils_click.AliasedShortMatchGroup)
@utils_click.requires_project
def create():
    '''
    Create a new component in the project.
    '''
    pass


@cli.group(cls=utils_click.AliasedShortMatchGroup)
def show():
    '''
    Multifunction command to list/show components, component files, and resources.
    '''
    pass


if __name__ == '__main__':
    cli()
