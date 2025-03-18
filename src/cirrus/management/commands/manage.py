import json
import logging
import os
import sys

from subprocess import CalledProcessError

import boto3
import botocore.exceptions
import click

from cirrus.lib.statedb import StateDB
from cirrus.management.deployment import WORKFLOW_POLL_INTERVAL, Deployment
from cirrus.management.utils.click import (
    AliasedShortMatchGroup,
    additional_variables,
    pass_session,
    silence_templating_errors,
)
from cirrus.management.utils.manage import (
    _get_execution,
    download_payload,
    execution_arn,
    include_user_vars,
    query_filters,
    raw_option,
)

logger = logging.getLogger(__name__)

pass_deployment = click.make_pass_decorator(Deployment)


@click.group(
    aliases=["mgmt"],
    cls=AliasedShortMatchGroup,
)
@click.argument(
    "deployment",
    metavar="DEPLOYMENT_NAME",
)
@pass_session
@click.pass_context
def manage(ctx, session: boto3.Session, deployment: str, profile: str | None = None):
    """
    Commands to run management operations against a cirrus deployment.
    """
    ctx.obj = Deployment.from_name(deployment, session=session)


@manage.command()
@pass_deployment
def show(deployment):
    """Show a deployment configuration"""
    color = "blue"
    click.secho(json.dumps(deployment.environment, indent=4), fg=color)


@manage.command("run-workflow")
@click.option(
    "-t",
    "--timeout",
    type=int,
    default=3600,
    help="Maximum time (seconds) to allow for the workflow to complete",
)
@click.option(
    "-p",
    "--poll-interval",
    type=int,
    default=WORKFLOW_POLL_INTERVAL,
    help="Time (seconds) to dwell between polling for workflow status",
)
@raw_option
@pass_deployment
def run_workflow(deployment, timeout, raw, poll_interval):
    """Pass a payload (from stdin) off to a deployment, wait for the workflow to finish,
    retrieve and return its output payload"""
    payload = json.loads(sys.stdin.read())

    output = deployment.run_workflow(
        payload=payload,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    click.echo(json.dump(output, sys.stdout, indent=4 if not raw else None))


@manage.command("get-payload")
@click.argument(
    "payload-id",
)
@raw_option
@pass_deployment
def get_payload(deployment: Deployment, payload_id, raw):
    """Get a payload from S3 using its ID"""

    if raw:
        download_payload(deployment, payload_id, sys.stdout.buffer)
    else:
        import io

        with io.BytesIO() as b:
            download_payload(deployment, payload_id, b)
            b.seek(0)
            json.dump(json.load(b), sys.stdout, indent=4)

    # ensure we end with a newline
    click.echo("")


@manage.command("get-execution")
@execution_arn
@raw_option
@pass_deployment
def get_execution(deployment, arn, payload_id, raw):
    """Get a workflow execution using its ARN or its input payload ID"""
    execution = _get_execution(deployment, arn, payload_id)

    if raw:
        click.echo(execution)
    else:
        click.echo(json.dumps(execution, indent=4, default=str))


@manage.command("get-execution-input")
@execution_arn
@raw_option
@pass_deployment
def get_execution_input(deployment, arn, payload_id, raw):
    """Get a workflow execution's input payload using its ARN or its input payload ID"""
    _input = json.loads(_get_execution(deployment, arn, payload_id)["input"])

    if raw:
        click.echo(_input)
    else:
        click.echo(json.dumps(_input, indent=4, default=str))


@manage.command("get-execution-output")
@execution_arn
@raw_option
@pass_deployment
def get_execution_output(deployment, arn, payload_id, raw):
    """Get a workflow execution's output payload using its ARN or its input
    payload ID"""
    output = json.loads(_get_execution(deployment, arn, payload_id)["output"])

    if raw:
        click.echo(output)
    else:
        click.echo(json.dumps(output, indent=4, default=str))


@manage.command("get-state")
@click.argument(
    "payload-id",
)
@pass_deployment
def get_state(deployment: Deployment, payload_id):
    """Get the statedb record for a payload ID"""
    state = deployment.get_payload_state(payload_id)
    click.echo(json.dumps(state, indent=4))


@manage.command()
@pass_deployment
def process(deployment: Deployment):
    """Enqueue a payload (from stdin) for processing"""
    click.echo(json.dumps(deployment.process_payload(sys.stdin), indent=4))


@manage.command()
@click.argument(
    "lambda-name",
)
@pass_session
@pass_deployment
def invoke_lambda(deployment: Deployment, session, lambda_name):
    """Invoke lambda with event (from stdin)"""
    click.echo(
        json.dumps(
            deployment.invoke_lambda(sys.stdin.read(), lambda_name, session),
            indent=4,
        ),
    )


@manage.command("template-payload")
@additional_variables
@silence_templating_errors
@include_user_vars
@pass_deployment
def template_payload(
    deployment,
    additional_variables,
    silence_templating_errors,
    include_user_vars,
):
    """Template a payload using a deployment's vars"""
    click.echo(
        deployment.template_payload(
            sys.stdin.read(),
            additional_variables,
            silence_templating_errors,
            include_user_vars,
        ),
    )


@manage.command(
    "exec",
    context_settings={
        "ignore_unknown_options": True,
    },
)
@click.argument(
    "command",
    nargs=-1,
)
@include_user_vars
@pass_deployment
@click.pass_context
def _exec(ctx, deployment, command, include_user_vars):
    """Run an executable with the deployment environment vars loaded"""
    if not command:
        return
    deployment.exec(command, include_user_vars=include_user_vars)


@manage.command(
    "call",
    context_settings={
        "ignore_unknown_options": True,
    },
)
@click.argument(
    "command",
    nargs=-1,
)
@include_user_vars
@pass_deployment
@click.pass_context
def _call(ctx, deployment, command, include_user_vars):
    """Run an executable, in a new process, with the deployment environment
    vars loaded"""
    if not command:
        return
    try:
        deployment.call(command, include_user_vars=include_user_vars)
    except CalledProcessError as cpe:
        sys.exit(cpe.returncode)


@manage.command()
@pass_session
@pass_deployment
@click.pass_context
def list_lambdas(ctx, deployment: Deployment, session):
    """List lambda functions"""
    click.echo(
        json.dumps(
            {"Functions": deployment.get_lambda_functions(session)},
            indent=4,
            default=str,
        ),
    )


# set each to option or try and set up a dictionary with typing for cleaner input
@manage.command("get-records")
@query_filters
@raw_option
@pass_session
@pass_deployment
@click.pass_context
def get_records(
    ctx,
    deployment: Deployment,
    session,
    raw,
    collections,
    workflow_name,
    state,
    since,
    error_prefix,
    limit=100,
):
    """Query multiple records from state DB using filter options"""
    click.echo(f"filters: limit: {limit} state: {state}")
    os.environ.update(deployment.environment)
    statedb = StateDB()
    query_args = {
        "collections_workflow": collections,
        "workflow-name": workflow_name,
        "state": state,
        "since": since,
        "limit": limit,
        "error-prefix": error_prefix,
    }

    # get items and make query
    items = statedb.get_items_page(**query_args)

    # loop through returned items, get each item and send to stdout for piping,
    for item in items["items"]:
        try:
            print(item)  # noqa: T201
            import io

            with io.BytesIO() as b:
                download_payload(deployment, "payload_id", b)
                b.seek(0)
                payload = json.load(b)
                # TODO: set payload 'replace' to true
                payload["replace"] = True
                json.dump(payload, sys.stdout, indent=4)
        except botocore.exceptions.ClientError as e:
            # TODO: understand why this is a ClientError even
            #   when it seems like it should be a NoKeyError
            logger.error(e)


# check-pipeline
#   - this is like failmgr check
#   - not sure how to reconcile with cache above
#   - maybe need subcommand for everything it can do
