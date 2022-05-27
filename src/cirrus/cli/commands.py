import sys
import click

from pathlib import Path
from pkg_resources import iter_entry_points

from cirrus.cli import constants
from cirrus.core.project import Project
from cirrus.cli.utils import (
    logging,
    click as utils_click,
)


logger = logging.getLogger(__name__)


@utils_click.plugin_entrypoint('cirrus.commands')
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
@click.pass_context
@logging.verbosity()
def cli(ctx, verbose, cirrus_dir=None):
    if cirrus_dir:
        project = Project(cirrus_dir)
    else:
        project = Project.resolve()

    ctx.obj = project

    for group in project.groups:
        if hasattr(group, 'add_create_command'):
            group.add_create_command(create)
        if hasattr(group, 'add_show_command'):
            group.add_show_command(show)


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
    Project.new(directory)
    click.secho(
        f"Succesfully initialized project in '{directory}'.",
        err=True,
        fg='green',
    )


@cli.command()
@utils_click.requires_project
def build(project):
    '''
    Build the cirrus configuration into a serverless.yml.
    '''
    project.build()


@cli.command()
@utils_click.requires_project
def clean(project):
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
def serverless(project, sls_args):
    '''
    Run serverless within the cirrus build directory.
    '''
    import os

    bd = project.build_dir
    if not bd.is_dir():
        logger.error('No build directory; have you run a build?')
        sys.exit(2)

    sls = project.path.joinpath('node_modules', 'serverless', 'bin', 'serverless.js')
    if not sls.is_file():
        logger.error('No serverless binary; have you run `npm install`?')
        sys.exit(1)

    os.chdir(bd)
    os.execv(sls, ['serverless'] + list(sls_args))


@cli.group(cls=utils_click.AliasedShortMatchGroup)
@utils_click.requires_project
def create(project):
    '''
    Create a new component in the project.
    '''
    pass


@cli.group(cls=utils_click.AliasedShortMatchGroup)
def show():
    '''
    Multifunction command to list/show components, files, etc.
    '''
    pass


@show.command()
def plugins():
    '''
    View installed plugins.
    '''
    try:
        from importlib import metadata as _metadata
    except ImportError:
        import importlib_metadata as _metadata

    for entry_point in iter_entry_points('cirrus.plugins'):
        color = 'blue'
        name = entry_point.name

        try:
            metadata = _metadata.metadata(name)
        except _metadata.PackageNotFoundError:
            desc = None
            color = 'red'
            name += ' (unknown package)'
        else:
            desc = metadata['Summary']

        click.echo('{}{}'.format(
            click.style(
                f'{name}:',
                fg=color,
            ),
            f' {desc}' if desc else '',
        ))


if __name__ == '__main__':
    cli()
