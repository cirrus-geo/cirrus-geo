from cirrus.cli.utils.yaml import NamedYamlable


DEFAULT_CONFIG = {
    'backend': 'serverless',
    'sources': {
        'feeders': ['./feeders'],
        'tasks': ['./tasks'],
        'workflows': ['./workflows'],
    },
}


class Config(NamedYamlable):
    pass
