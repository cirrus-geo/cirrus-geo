class CirrusError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ConfigError(CirrusError):
    pass


class ComponentError(CirrusError):
    pass


class CloudFormationError(CirrusError):
    pass


class CloudFormationSkipped(CloudFormationError):  # noqa: N818
    pass


class DuplicateRequirement(ComponentError):  # noqa: N818
    pass


class MissingHandler(CirrusError):  # noqa: N818
    pass
