import sys
import click

from cirrus.config import config as _config, CONFIG_VAR
from cirrus.project import init


PROG='cirrus'
DESC=''


@click.group()
@click.option(
    '-c',
    '--config',
    envvar=CONFIG_VAR,
)
def main(config=None):
    '''
    cli for cirrus, a severless STAC-based processing pipeline
    '''
    if config:
        _config.set_source(config)
    else:
        _config.resolve()


main.add_command(init)


if __name__ == '__main__':
    main()
