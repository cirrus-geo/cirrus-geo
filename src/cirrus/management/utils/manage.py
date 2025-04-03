import logging

from functools import wraps

import botocore
import click

from click_option_group import (
    RequiredMutuallyExclusiveOptionGroup,
    optgroup,
)

from cirrus.management.deployment import Deployment

logger = logging.getLogger(__name__)


def _get_execution(deployment: Deployment, arn=None, payload_id=None):
    if payload_id:
        return deployment.get_execution_by_payload_id(payload_id)
    return deployment.get_execution(arn)


def query_filters(func):
    # reverse order because not using decorators to keep command clean
    """Available inputs to filter stateDB query"""
    func = optgroup.option(
        "--collection-workflow",
        help="The collection to filter on",
        required=True,
    )(func)
    func = optgroup.option(
        "--state",
        help="Execution state to filter on",
    )(func)
    func = optgroup.option(
        "--since",
        help="Time filter of how far back to search records",
    )(func)
    func = optgroup.option(
        "--limit",
        help="limit the options returned ",
        default=100,
        max=50000,
    )(func)
    func = optgroup.option(
        "--error-prefix",
        help="The error prefix to filter on",
    )(func)
    func = optgroup.group(
        "StateDB Query Filters",
        help="Parameters that can be used to filter your search query of state DB",
    )(func)
    return func  # noqa: RET504


def execution_arn(func):
    # reverse order because not using decorators
    func = optgroup.option(
        "--payload-id",
        help="payload ID (resolves to latest execution ARN)",
    )(func)
    func = optgroup.option(
        "--arn",
        help="Execution ARN",
    )(func)
    func = optgroup.group(
        "Identifier",
        cls=RequiredMutuallyExclusiveOptionGroup,
        help="Identifer type and value to get execution",
    )(func)
    return func  # noqa: RET504


def raw_option(func):
    return click.option(
        "-r",
        "--raw",
        is_flag=True,
        help="Do not pretty-format the response",
    )(func)


def include_user_vars(func):
    @click.option(
        "--include-user-vars/--exclude-user-vars",
        default=True,
        help="Whether or not to load deployment's user vars into environment",
    )
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def download_payload(deployment: Deployment, payload_id, output_fileobj):
    try:
        deployment.get_payload_by_id(payload_id, output_fileobj)
    except botocore.exceptions.ClientError as e:
        # TODO: understand why this is a ClientError even
        #   when it seems like it should be a NoKeyError
        logger.error(e)
