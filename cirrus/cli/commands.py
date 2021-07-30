import os
import click

from pathlib import Path
from cirrus.cli.project import project
from cirrus.cli.feeders import Feeder
from cirrus.cli.tasks import Task
from cirrus.cli.workflows import Workflow
#from cirrus.cli.tasks.commands import cli as cli_tasks
#from cirrus.cli.workflows.commands import cli as cli_workflows


PROG = 'cirrus'
DESC = 'cli for cirrus, a severless STAC-based processing pipeline'


@click.group(
    name=PROG,
    help=DESC,
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
def cli(cirrus_dir=None):
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


cli.add_command(Feeder.cli)
cli.add_command(Task.cli)
cli.add_command(Workflow.cli)


if __name__ == '__main__':
    cli()