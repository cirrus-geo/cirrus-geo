import logging

import boto3
import click

from cirrus.management.deployment import Deployment
from cirrus.management.utils.click import pass_session

logger = logging.getLogger(__name__)


@click.command()
@pass_session
def list_deployments(session: boto3.Session) -> None:
    """
    List all project deployments (accessible via current AWS role)
    """
    for deployment_name in Deployment.yield_deployments(session=session):
        click.echo(deployment_name)
