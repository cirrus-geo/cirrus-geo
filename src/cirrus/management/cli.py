import sys

from collections.abc import Callable
from functools import wraps
from typing import Any

import boto3
import botocore.exceptions
import click

from cirrus import exceptions
from cirrus.management.utils import click as utils_click
from cirrus.management.utils import logging

logger = logging.getLogger(__name__)


from cirrus.management.commands.deployments import list_deployments  # noqa: E402
from cirrus.management.commands.manage import manage as manage_group  # noqa: E402
from cirrus.management.commands.payload import payload as payload_group  # noqa: E402
from cirrus.management.exceptions import SSOError  # noqa: E402


def handle_sso_error(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except (
            botocore.exceptions.UnauthorizedSSOTokenError,
            botocore.exceptions.TokenRetrievalError,
            botocore.exceptions.SSOTokenLoadError,
        ) as e:
            raise SSOError(
                "SSO session not authorized. Run `aws sso login` and try again.",
            ) from e

    return wrapper


class MainGroup(utils_click.AliasedShortMatchGroup):
    def invoke(self, *args, **kwargs) -> Any:
        try:
            return handle_sso_error(super().invoke)(*args, **kwargs)
        except exceptions.CirrusError as e:
            logger.error(
                e,
                exc_info=(
                    e if logger.getEffectiveLevel() < logging.logging.INFO else False
                ),
            )
            sys.exit(e.exit_code)


@click.group(
    name="cirrus",
    help="CLI for running operational commands against cirrus deployments",
    cls=MainGroup,
)
@click.option(
    "--profile",
    help="AWS CLI profile name to use for session",
)
@click.option(
    "--region",
    help="AWS region name to use for session",
)
@click.pass_context
@logging.verbosity()
def cli(ctx, verbose, profile: str | None = None, region: str | None = None) -> None:
    ctx.obj = boto3.Session(profile_name=profile, region_name=region)


cli.add_command(list_deployments)
cli.add_command(manage_group)
cli.add_command(payload_group)


if __name__ == "__main__":
    cli()
