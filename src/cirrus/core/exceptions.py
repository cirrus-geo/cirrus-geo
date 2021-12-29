class CirrusError(Exception):
    pass


class ConfigError(CirrusError):
    pass


class ComponentError(CirrusError):
    pass

class CloudFormationError(CirrusError):
    pass

class CloudFormationSkipped(CloudFormationError):
    pass
