import logging
import logging.config

import click

DEFAULT_LEVEL = logging.WARNING


def verbosity(**kwargs):
    def _set_level(ctx, self, count):
        level = DEFAULT_LEVEL - count * 10
        logging.getLogger().setLevel(level)

    def wrapper(func):
        return click.option(
            "-v",
            "--verbose",
            help="Increase logging level. Can be specified multiple times.",
            is_eager=True,
            count=True,
            callback=_set_level,
            **kwargs,
        )(func)

    return wrapper


def make_logging_config(level):
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "click": {
                "class": "cirrus.cli.utils.logging_classes.ClickFormatter",
            },
        },
        "handlers": {
            "cli": {
                "class": "cirrus.cli.utils.logging_classes.ClickHandler",
                "formatter": "click",
            },
        },
        "loggers": {
            "cirrus.cli": {
                "handlers": ["cli"],
                "propagate": False,
            },
            "cirrus.core": {
                "handlers": ["cli"],
                "propagate": False,
            },
        },
    }


def configure(level=DEFAULT_LEVEL):
    logging.config.dictConfig(make_logging_config(level))


configure()
getLogger = logging.getLogger  # noqa: N816
