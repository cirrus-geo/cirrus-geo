import logging
import logging.config

from os import getenv
from typing import Any

config: dict[str, Any] = {
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
            "class": "pythonjsonlogger.json.JsonFormatter",
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
        "cirrus.lib": {
            "handlers": ["standard"],
            "level": getenv("CIRRUS_LOG_LEVEL", "DEBUG"),
        },
    },
}


logging.config.dictConfig(config)


class CirrusLoggerAdapter(logging.LoggerAdapter):
    def __init__(
        self,
        logger_name: str | None = None,
        payload: dict[str, Any] | None = None,
        aws_request_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(logging.getLogger(logger_name))

        if (
            self.logger.parent
            and self.logger.parent.name
            and self.logger.parent.name in config["loggers"]
        ):
            # this prevents double-logging in AWS Cloudwatch for cirrus loggers
            self.logger.parent.propagate = False

        self.reset_extra(payload, aws_request_id, **kwargs)

    def process(
        self,
        msg: str,
        kwargs: Any,
    ) -> tuple[str, Any]:
        # allow passing an "extra" dict on individual log calls
        if self.extra is not None:
            kwargs["extra"] = {**self.extra, **kwargs.get("extra", {})}
        return msg, kwargs

    def reset_extra(
        self,
        payload: dict[str, Any] | None = None,
        aws_request_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        if payload_id := payload.get("id") if payload else None:
            kwargs["id"] = payload_id

        if stac_version := payload.get("stac_version") if payload else None:
            kwargs["stac_version"] = stac_version

        if aws_request_id:
            kwargs["aws_request_id"] = aws_request_id

        self.extra = kwargs


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
