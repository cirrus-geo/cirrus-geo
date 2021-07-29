class CirrusError(Exception):
    pass


class ConfigError(CirrusError):
    pass


class ResourceLoadError(FileNotFoundError):
    pass
