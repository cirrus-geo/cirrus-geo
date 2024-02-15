class NoUrlError(ValueError):
    """Exception class for when a payload does not have a URL."""

    pass


class InvalidInput(Exception):  # noqa: N818
    """Exception class for when processing fails due to invalid input."""

    pass
