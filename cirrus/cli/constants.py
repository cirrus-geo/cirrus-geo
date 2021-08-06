PROG = 'cirrus'
DESC = 'cli for cirrus, a severless STAC-based processing pipeline'

DEFAULT_CONFIG_FILENAME = 'cirrus.yml'
DEFAULT_SERVERLESS_FILENAME = 'serverless.yml'
DEFAULT_BUILD_DIR_NAME = '.cirrus'

SUPPORTED_BACKENDS = [
    'serverless',
]

SERVERLESS_PLUGINS = [
  'serverless-python-requirements',
  'serverless-step-functions',
  'serverless-pseudo-parameters',
  'serverless-iam-roles-per-function',
]
