DEFAULT_CONFIG_FILENAME = "cirrus.yml"
DEFAULT_SERVERLESS_FILENAME = "serverless.yml"
DEFAULT_BUILD_DIR_NAME = ".cirrus"

DEFAULT_DOT_DIR_NAME = ".cirrus"
DEFAULT_BUILD_DIR_NAME = "build"

DEFAULT_GIT_IGNORE = """__pycache__/
node_modules/
.DS_Store
.cirrus
"""

SERVERLESS = {"serverless": "~3.18.0"}
SERVERLESS_PLUGINS = {
    "serverless-python-requirements": "~5.4.0",
    "serverless-step-functions": "~3.7.0",
    "serverless-iam-roles-per-function": "~3.2.0",
}

BUILT_IN = "built-in"
