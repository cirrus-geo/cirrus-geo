import logging

import click

# Inspired from https://github.com/click-contrib/click-log


class ClickFormatter(logging.Formatter):
    colors = {
        "error": {"fg": "red"},
        "exception": {"fg": "red"},
        "critical": {"fg": "red"},
        "debug": {"fg": "blue"},
        "warning": {"fg": "yellow"},
    }

    def format(self, record):
        msg = super().format(record)
        level = record.levelname.lower()
        if level in self.colors:
            msg = click.style(f"{msg}", **self.colors[level])
        return msg


class ClickHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            record.levelname.lower()
            click.echo(msg, err=True)
        except Exception:
            self.handleError(record)
