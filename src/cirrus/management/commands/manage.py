import json
import logging
import sys

from functools import wraps
from subprocess import CalledProcessError

import boto3
import botocore.exceptions
import click

from click_option_group import RequiredMutuallyExclusiveOptionGroup, optgroup

from cirrus.management.deployment import WORKFLOW_POLL_INTERVAL, Deployment
from cirrus.management.utils.click import (
    AliasedShortMatchGroup,
    additional_variables,
    pass_session,
    silence_templating_errors,
)

logger = logging.getLogger(__name__)

pass_deployment = click.make_pass_decorator(Deployment)


def _get_execution(deployment, arn=None, payload_id=None):
    if payload_id:
        return deployment.get_execution_by_payload_id(payload_id)
    return deployment.get_execution(arn)


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
    click.secho(deployment.asjson(indent=4), fg=color)


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
def get_payload(deployment, payload_id, raw):
    """Get a payload from S3 using its ID"""

    def download(output_fileobj):
        try:
            deployment.get_payload_by_id(payload_id, output_fileobj)
        except botocore.exceptions.ClientError as e:
            # TODO: understand why this is a ClientError even
            #   when it seems like it should be a NoKeyError
            logger.error(e)

    if raw:
        download(sys.stdout.buffer)
    else:
        import io

        with io.BytesIO() as b:
            download(b)
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
def get_state(deployment, payload_id):
    """Get the statedb record for a payload ID"""
    state = deployment.get_payload_state(payload_id)
    click.echo(json.dumps(state, indent=4))


@manage.command()
@pass_deployment
def process(deployment):
    """Enqueue a payload (from stdin) for processing"""
    click.echo(json.dumps(deployment.process_payload(sys.stdin), indent=4))


@manage.command()
@click.argument(
    "lambda-name",
)
@pass_deployment
def invoke_lambda(deployment, lambda_name):
    """Invoke lambda with event (from stdin)"""
    click.echo(
        json.dumps(deployment.invoke_lambda(sys.stdin.read(), lambda_name), indent=4),
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
@pass_deployment
@click.pass_context
def list_lambdas(ctx, deployment):
    """List lambda functions"""
    click.echo(
        json.dumps(
            {"Functions": deployment.get_lambda_functions()},
            indent=4,
            default=str,
        ),
    )


# check-pipeline
#   - this is like failmgr check
#   - not sure how to reconcile with cache above
#   - maybe need subcommand for everything it can do
