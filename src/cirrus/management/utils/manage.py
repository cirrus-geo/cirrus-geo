import logging

from datetime import timedelta
from functools import wraps

import click

from click_option_group import (
    RequiredMutuallyExclusiveOptionGroup,
    optgroup,
)

from cirrus.lib.enums import StateEnum
from cirrus.lib.utils import parse_since
from cirrus.management.deployment import Deployment

logger = logging.getLogger(__name__)


class SinceType(click.ParamType):
    """Custom Click type for --since option.

    Validates that the input is an integer followed by a unit letter and
    converts it to a timedelta:
    - 'd' for days
    - 'h' for hours
    - 'm' for minutes

    Examples: '7d', '24h', '30m'
    """

    name = "since"

    def convert(self, value, param, ctx) -> timedelta | None:
        if value is None:
            return value
        try:
            return parse_since(value)
        except ValueError as e:
            self.fail(str(e), param, ctx)


SINCE = SinceType()


def _get_execution(deployment: Deployment, arn=None, payload_id=None):
    if payload_id:
        return deployment.get_execution_by_payload_id(payload_id)
    return deployment.get_execution(arn)


def query_filters(func):
    # reverse order because not using decorators to keep command clean
    """Available inputs to filter stateDB query"""
    func = optgroup.option(
        "--collections-workflow",
        help="The collections-workflow field to filter on",
        required=True,
    )(func)
    func = optgroup.option(
        "--state",
        help="Execution state to filter on",
        type=click.Choice([state.value for state in StateEnum]),
    )(func)
    func = optgroup.option(
        "--since",
        help=(
            "Time filter. Integer followed by a unit letter "
            "(d=days, h=hours, m=minutes), e.g., '7d', '24h', '30m'"
        ),
        type=SINCE,
    )(func)
    func = optgroup.option(
        "--limit",
        help="Maximum number of payloads to return",
        type=click.IntRange(1, 50000),
    )(func)
    func = optgroup.option(
        "--error-prefix",
        help="The error prefix to filter on",
    )(func)
    func = optgroup.group(
        "Query Filters",
        help="Parameters to filter query of state DB to retrieve payloads",
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


def rerun_option(func):
    return click.option(
        "--rerun",
        is_flag=True,
        help="Rerun payloads",
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
