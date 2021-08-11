import os
import click
import sys

from pathlib import Path
from cirrus.cli import constants
from cirrus.cli.project import project
from cirrus.cli.exceptions import ComponentError
from cirrus.cli.component import (
    registered_component_types,
    registered_component_types_plural,
)
from cirrus.cli.utils import logging
from cirrus.cli.utils.decorators import requires_project

# unused, but imports required so they register
from cirrus.cli.feeders import Feeder
from cirrus.cli.tasks import Task
from cirrus.cli.workflows import Workflow


logger = logging.getLogger(__name__)


@click.group(
    name=constants.PROG,
    help=constants.DESC,
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
        directory = Path(os.getcwd())
    project.new(directory)
    click.secho(
        f"Succesfully initialized project in '{directory}'.",
        err=True,
        fg='green',
    )


@cli.command()
@requires_project
def build():
    '''
    Build the cirrus configuration into a serverless.yml.
    '''
    project.build()


@cli.command(name='list')
@click.argument(
    'component-types',
    metavar='component-type(s)',
    required=True,
    nargs=-1,
    type=click.Choice(
        ['all'] + list(registered_component_types_plural.keys()),
        case_sensitive=False,
    )
)
def _list(component_types):
    '''
    List all components of the given TYPE(s).

    TYPEs include 'feeders', 'tasks', and 'workflows', as well as the
    special type 'all' which will list all components of all TYPEs.
    '''
    if 'all' in component_types:
        component_types = registered_component_types_plural

    display_type = len(component_types) > 1
    for index, component_type in enumerate(component_types):
        if display_type:
            click.secho(
                f'{component_type.capitalize()}',
                fg='green',
            )

        component_type = registered_component_types_plural[component_type]

        for component in component_type.find():
            click.echo('{}{}'.format(
                click.style(f'{component.display_name}:', fg='blue'),
                f' {component.description}' if component.description else '',
            ))

        if index + 1 < len(component_types):
            click.echo('')


# TODO: decorators for component_type and component_types
@cli.command()
@click.argument(
    'component-type',
    metavar='component-type',
    required=True,
    type=click.Choice(
        list(registered_component_types.keys()),
        case_sensitive=False,
    )
)
@click.argument(
    'component-name',
    metavar='component-name',
)
@requires_project
def new(component_type, component_name):
    '''
    Create a new COMPONENT_TYPE of name COMPONENT_NAME.
    '''
    _component_type = registered_component_types[component_type]
    try:
        _component_type.create(component_name)
    except ComponentError as e:
        logger.error(e)
        sys.exit(1)
    else:
        # TODO: logging level for "success" on par with warning?
        click.secho(
            f'{component_type} {component_name} created',
            err=True,
            fg='green',
        )


@cli.command()
@click.argument(
    'component-type',
    metavar='component-type',
    required=True,
    type=click.Choice(
        [k for k, v in registered_component_types.items() if hasattr(v, 'readme')],
        case_sensitive=False,
    )
)
@click.argument(
    'component-name',
    metavar='component-name',
)
def readme(component_type, component_name):
    '''
    Display a component README.
    '''
    # TODO: make this a 'show' command with the usage like
    #    cirrus show feeder feed-stac-s3 [ FILES... ]
    #  and use rich to determine how to show files if in terminal
    #
    #  Should support "showing" nont component resources like
    #    cirrus show resource [ NAME ]
    from cirrus.cli.utils.console import console
    from rich.markdown import Markdown
    component_type = registered_component_types[component_type]
    component = component_type.find_first(component_name)
    if not component:
        logger.error(f"Unable to find {self.component_type} with name '{name}'.")
        return

    if component.readme.content is None:
        logger.error(f"{self.component_type.capitalize()} '{name}' has no README.")
        return

    console.print(Markdown(component.readme.content))


if __name__ == '__main__':
    cli()
