import json
import logging
import sys

import click

from cirrus.management.utils.click import (
    AliasedShortMatchGroup,
    additional_variables,
    silence_templating_errors,
)

logger = logging.getLogger(__name__)


@click.group(
    cls=AliasedShortMatchGroup,
)
def payload():
    """
    Commands for working with payloads.
    """
    pass


@payload.command()
def validate():
    """Validate an input payload (from stdin) is a valid cirrus payload"""
    from cirrus.lib.cirrus_payload import CirrusPayload

    payload = sys.stdin.read()
    CirrusPayload(**json.loads(payload)).validate()


@payload.command("get-id")
def get_id():
    """Retrieve or generate an ID for an input payload (from stdin)"""
    from cirrus.lib.cirrus_payload import CirrusPayload

    payload = sys.stdin.read()
    click.echo(
        CirrusPayload(**json.loads(payload), set_id_if_missing=True)["id"],
    )


@payload.command()
@additional_variables
@silence_templating_errors
def template(
    additional_variables: dict[str, str],
    silence_templating_errors: bool,
):
    """Template a payload (from stdin) with user supplied vars with '$' based
    substitution"""
    from cirrus.management.utils.templating import template_payload

    click.echo(
        template_payload(
            sys.stdin.read(),
            additional_variables,
            silence_templating_errors,
        ),
    )
