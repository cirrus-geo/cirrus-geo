DEFAULT_CONFIG_FILENAME = 'cirrus.yml'
DEFAULT_SERVERLESS_FILENAME = 'serverless.yml'
DEFAULT_BUILD_DIR_NAME = '.cirrus'

SERVERLESS = {'serverless': '^1.83.1'}
SERVERLESS_PLUGINS = {
    'serverless-python-requirements': '~5.1.0',
    'serverless-step-functions': '~2.27.1',
    'serverless-pseudo-parameters': '~2.5.0',
    'serverless-iam-roles-per-function': '~3.1.0',
  }
