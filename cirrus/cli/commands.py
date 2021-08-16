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
    import os

    if not directory:
        directory = Path(os.getcwd())
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


@cli.group()
@utils_click.requires_project
def create():
    '''
    Create a new component in the project.
    '''
    pass


def add_component_create(component_type):
    if not component_type.user_extendable:
        return

    @create.command(
        name=component_type.component_type,
    )
    @click.argument(
        'name',
        metavar='name',
    )
    def _show(name):
        import sys
        from cirrus.cli.exceptions import ComponentError

        try:
            component_type.create(name)
        except ComponentError as e:
            logger.error(e)
            sys.exit(1)
        else:
            # TODO: logging level for "success" on par with warning?
            click.secho(
                f'{component_type.component_type} {name} created',
                err=True,
                fg='green',
            )


@cli.group()
def show():
    '''
    Multifunction command to list/show components/files/resources.
    '''
    pass


def add_component_show(component_type):
    @show.command(
        name=component_type.component_type,
    )
    @click.argument(
        'name',
        metavar='name',
        required=False,
    )
    @click.argument(
        'filename',
        metavar='filename',
        required=False,
    )
    def _show(name=None, filename=None):
        components = component_type.find(name=name)
        if name is None:
            for component in components:
                component.list_display()
            return

        component = next(components)
        if filename is None:
            component.detail_display()
            return

        try:
            component.files[filename].show()
        except KeyError:
            logger.error("Cannot show: unknown file '%s'", filename)

# TODO: add show for resources


if __name__ == '__main__':
    cli()
