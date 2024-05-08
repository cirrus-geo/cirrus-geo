class NoUrlError(ValueError):
    """Exception class for when a payload does not have a URL."""

    pass


class EventsDisabledError(RuntimeError):
    """Exception class for EventDB to throw when it is disabled."""

    pass
