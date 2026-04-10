from typing import Literal

from cirrus.exceptions import CirrusError


class SSOError(CirrusError):
    pass


class DeploymentConfigurationError(CirrusError):
    pass


class DeploymentNotFoundError(CirrusError):
    def __init__(self, deployment_name, *args, **kwargs):
        msg = f"Deployment not found: '{deployment_name}'"
        super().__init__(msg, *args, **kwargs)


class MissingParameterError(CirrusError):
    def __init__(self, missing: str, *extra_missing: str, **kwargs):
        msg = f"A required environment variable(s) was not found: {
            ', '.join((missing, *extra_missing))
        }"
        super().__init__(msg, **kwargs)


class StatsUnavailableError(CirrusError):
    def __init__(self, *args, **kwargs):
        msg = "Stats not available because timeseries database is not configured"
        super().__init__(msg, *args, **kwargs)


class NoPayloadUrlError(CirrusError):
    def __init__(
        self,
        payload_id: str,
        direction: Literal["input", "output"],
        *args,
        **kwargs,
    ) -> None:
        msg = f"Could not resolve url for {direction} payload: {payload_id}"
        super().__init__(msg, *args, **kwargs)
