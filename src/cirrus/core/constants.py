DEFAULT_CONFIG_FILENAME = 'cirrus.yml'
DEFAULT_SERVERLESS_FILENAME = 'serverless.yml'
DEFAULT_BUILD_DIR_NAME = '.cirrus'

SERVERLESS = {'serverless': '^2.70.0'}
SERVERLESS_PLUGINS = {
    'serverless-python-requirements': '^5.2.2',
    'serverless-step-functions': '^3.4.0',
    'serverless-pseudo-parameters': '^2.6.1',
    'serverless-iam-roles-per-function': '^3.2.0',
  }
