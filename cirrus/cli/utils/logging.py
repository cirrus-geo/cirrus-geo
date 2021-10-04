import logging
import click


# Inspired from https://github.com/click-contrib/click-log


DEFAULT_LEVEL = logging.WARNING


class ClickFormatter(logging.Formatter):
    colors = {
        'error': {'fg': 'red'},
        'exception': {'fg': 'red'},
        'critical': {'fg': 'red'},
        'debug': {'fg': 'blue'},
        'warning': {'fg': 'yellow'},
    }

    def format(self, record):
        if not record.exc_info:
            level = record.levelname.lower()
            msg = record.getMessage()
            if level in self.colors:
                msg = click.style('{}'.format(msg), **self.colors[level])
            return msg
        return super().format(self, record)


class ClickHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = ClickFormatter()

    def emit(self, record):
        try:
            msg = self.format(record)
            record.levelname.lower()
            click.echo(msg, err=True)
        except Exception:
            self.handleError(record)


def verbosity(**kwargs):
    def _set_level(ctx, self, count):
        level = DEFAULT_LEVEL - count * 10
        logging.getLogger().setLevel(level)

    def wrapper(func):
        return click.option(
            '-v',
            '--verbose',
            help='Increase logging level. Can be specified multiple times.',
            is_eager=True,
            count=True,
            callback=_set_level,
            **kwargs,
        )(func)
    return wrapper


def configure(level=DEFAULT_LEVEL):
    logging.basicConfig(handlers=_handlers, level=level)


_handlers = [ClickHandler()]
configure()
getLogger = logging.getLogger
