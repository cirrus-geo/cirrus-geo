PROG = 'cirrus'
DESC = 'cli for cirrus, a severless STAC-based processing pipeline'

DEFAULT_CONFIG_FILENAME = 'cirrus.yml'
DEFAULT_SERVERLESS_FILENAME = 'serverless.yml'
DEFAULT_BUILD_DIR_NAME = '.cirrus'

SERVERLESS_PLUGINS = {
    'serverless-python-requirements': '^1.67.3',
    'serverless-step-functions': '^2.5.0',
    'serverless-pseudo-parameters': '^5.1.0',
    'serverless-iam-roles-per-function': '^2.27.1',
  }
