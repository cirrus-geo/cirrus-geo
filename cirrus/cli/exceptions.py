class CirrusError(Exception):
    pass


class ConfigError(CirrusError):
    pass


class ResourceError(CirrusError):
    pass

class ResourceLoadError(FileNotFoundError):
    pass
