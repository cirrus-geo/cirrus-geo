import logging
import logging.config
from os import getenv

config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        "json": {
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
        },
    },
    "handlers": {"standard": {"class": "logging.StreamHandler", "formatter": "json"}},
    "loggers": {
        "lambda_function": {
            "handlers": ["standard"],
            "level": getenv("CIRRUS_LOG_LEVEL", "DEBUG"),
        },
        "function": {
            "handlers": ["standard"],
            "level": getenv("CIRRUS_LOG_LEVEL", "DEBUG"),
        },
        "feeder": {
            "handlers": ["standard"],
            "level": getenv("CIRRUS_LOG_LEVEL", "DEBUG"),
        },
        "task": {
            "handlers": ["standard"],
            "level": getenv("CIRRUS_LOG_LEVEL", "DEBUG"),
        },
        "cirrus.lib2": {
            "handlers": ["standard"],
            "level": getenv("CIRRUS_LOG_LEVEL", "DEBUG"),
        },
    },
}


logging.config.dictConfig(config)


class DynamicLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, *args, keys=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.keys = keys

    def process(self, msg, kwargs):
        if self.keys is not None:
            kwargs["extra"] = {k: self.extra[k] for k in self.keys if k in self.extra}
        return (msg, kwargs)


def get_task_logger(*args, payload, **kwargs):
    _logger = logging.getLogger(*args, **kwargs)
    logger = DynamicLoggerAdapter(_logger, payload, keys=["id", "stac_version"])
    return logger


class defer:  # noqa: N801
    """Use this like a function to defer a expensive function call
    to run only when building a log message. That is, this class
    prevents expensive function calls for log arguments that will
    not be logged due to the current log level.

    Example usage:

        logger.debug(
            'Value: %s',
            defer(expensive_fn, arg1, arg2, kwarg1='value'),
        )

    In this example, the `expensive_fn` would only be run when the
    log level is less than or equal to DEBUG, and it would be called
    like:

        expensive_fn(arg1, arg2, kwarg1='value')
    """

    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        return str(self.func(*self.args, **self.kwargs))
