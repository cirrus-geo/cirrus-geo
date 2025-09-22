import json
import logging
import sys

from datetime import timedelta
from subprocess import CalledProcessError

import click

from boto3 import Session

from cirrus.lib.enums import StateEnum
from cirrus.management.deployment import WORKFLOW_POLL_INTERVAL, Deployment
from cirrus.management.utils.click import (
    AliasedShortMatchGroup,
    additional_variables,
    pass_session,
    silence_templating_errors,
)
from cirrus.management.utils.manage import (
    SINCE,
    _get_execution,
    execution_arn,
    include_user_vars,
    query_filters,
    raw_option,
    rerun_option,
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
@click.option(
    "--iam-arn",
    metavar="IAM_ROLE_ARN",
)
@pass_session
@click.pass_context
def manage(
    ctx,
    session: Session,
    deployment: str,
    iam_arn: str | None = None,
):
    """
    Commands to run management operations against a cirrus deployment.
    """
    ctx.obj = Deployment.from_name(deployment, session=session, iam_role_arn=iam_arn)


@manage.command()
@pass_deployment
def show(deployment: Deployment):
    """Show a deployment configuration"""
    color = "blue"
    click.secho(json.dumps(deployment.environment, indent=4), fg=color)


@manage.command("run-workflow")
@click.option(
    "-t",
    "--timeout",
    type=click.INT,
    default=3600,
    help="Maximum time (seconds) to allow for the workflow to complete",
)
@click.option(
    "-p",
    "--poll-interval",
    type=click.INT,
    default=WORKFLOW_POLL_INTERVAL,
    help="Time (seconds) to dwell between polling for workflow status",
)
@raw_option
@pass_deployment
def run_workflow(
    deployment: Deployment,
    timeout: int,
    poll_interval: int,
    raw: bool = False,
):
    """Pass a payload (from stdin) off to a deployment, wait for the workflow to finish,
    retrieve and return its output payload"""
    payload = json.loads(sys.stdin.read())

    output = deployment.run_workflow(
        payload=payload,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    click.echo(json.dumps(output, indent=(4 if not raw else None)))


@manage.command("get-payload")
@click.argument(
    "payload-id",
)
@raw_option
@pass_deployment
def get_payload(deployment: Deployment, payload_id: str, raw: bool = False):
    """Get a payload from S3 using its ID"""

    if raw:
        click.echo(deployment.fetch_payload(payload_id))
    else:
        json.dump(deployment.fetch_payload(payload_id), sys.stdout, indent=4)
        click.echo("")


@manage.command("get-execution")
@execution_arn
@raw_option
@pass_deployment
def get_execution(
    deployment: Deployment,
    arn: str | None,
    payload_id: str | None,
    raw: bool = False,
):
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
def get_execution_input(
    deployment: Deployment,
    arn: str | None,
    payload_id: str | None,
    raw: bool = False,
):
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
def get_execution_output(
    deployment: Deployment,
    arn: str | None,
    payload_id: str | None,
    raw: bool = False,
):
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
def get_state(deployment: Deployment, payload_id: str):
    """Get the statedb record for a payload ID"""
    state = deployment.get_payload_state(payload_id)
    click.echo(json.dumps(state, indent=4))


@manage.command()
@pass_deployment
def process(deployment: Deployment):
    """Enqueue a payload (from stdin) for processing"""
    click.echo(json.dumps(deployment.enqueue_payload(sys.stdin.read()), indent=4))


@manage.command()
@click.argument(
    "lambda-name",
)
@pass_session
@pass_deployment
def invoke_lambda(deployment: Deployment, session: Session, lambda_name: str):
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
    deployment: Deployment,
    silence_templating_errors: bool,
    include_user_vars: bool,
    additional_variables: dict[str, str],
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
def _exec(ctx, deployment: Deployment, command: str, include_user_vars: bool):
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
def _call(ctx, deployment: Deployment, command: str, include_user_vars: bool):
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
def list_lambdas(ctx, deployment: Deployment, session: Session):
    """List lambda functions"""
    click.echo(
        json.dumps(
            {"Functions": deployment.get_lambda_functions(session)},
            indent=4,
            default=str,
        ),
    )


@manage.command("get-payloads")
@rerun_option
@query_filters
@pass_deployment
def get_payloads(
    deployment: Deployment,
    collections_workflow: str,
    state: str | None,
    since: timedelta | None,
    error_prefix: str | None,
    limit: int | None,
    rerun: bool = False,
):
    """
    Retrieve a filtered set of payloads from S3 via querying the state DB for
    matching payload IDs
    Rerun flag alters payloads to enable rerunning payload
    """

    # send to stdout as NDJSON for piping
    for payload in deployment.yield_payloads(
        collections_workflow,
        limit,
        {"state": state, "since": since, "error_begins_with": error_prefix},
        rerun,
    ):
        click.echo(json.dumps(payload, default=str))


@manage.command("get-workflow-summary")
@click.argument("collections")
@click.argument("workflow_name")
@click.option(
    "--since",
    default=None,
    help=(
        "Only include items updated since this relative duration (e.g., 7d, 36h, 15m)"
    ),
    type=SINCE,
)
@click.option(
    "--limit",
    default=10000,
    show_default=True,
    type=click.INT,
    help="Limit the number of items considered for counts",
)
@pass_deployment
def get_workflow_summary(
    deployment: Deployment,
    collections: str,
    workflow_name: str,
    since: timedelta | None,
    limit: int,
):
    """Get item counts by state for a collections/workflow from DynamoDB"""
    summary = deployment.get_workflow_summary(
        collections,
        workflow_name,
        since,
        limit,
    )
    click.echo(json.dumps(summary, indent=2))


@manage.command("get-workflow-stats")
@pass_deployment
def get_workflow_stats(deployment: Deployment):
    """Get aggregate workflow state transition stats from Timestream"""
    stats = deployment.get_workflow_stats()
    click.echo(json.dumps(stats, indent=2))


@manage.command("get-workflow-items")
@click.argument("collections")
@click.argument("workflow_name")
@click.option(
    "--state",
    default=None,
    help="Filter by item state",
    type=click.Choice([state.value for state in StateEnum]),
)
@click.option(
    "--since",
    default=None,
    help=(
        "Only include items updated since this relative duration (e.g., 7d, 36h, 15m)"
    ),
    type=SINCE,
)
@click.option(
    "--limit",
    default=10,
    show_default=True,
    type=click.IntRange(1, 50000),
    help="Limit the number of items returned",
)
@click.option("--nextkey", default=None, help="Pagination key for next page")
@click.option(
    "--sort-ascending",
    is_flag=True,
    default=False,
    help="Sort results in ascending order",
)
@click.option(
    "--sort-index",
    default="updated",
    help="Index to sort by",
    type=click.Choice(["default", "updated", "state_updated"]),
)
@pass_deployment
def get_workflow_items(
    deployment: Deployment,
    collections: str,
    workflow_name: str,
    state: str | None,
    since: timedelta | None,
    limit: int,
    nextkey: str | None,
    sort_ascending: bool,
    sort_index: str,
):
    """Get items for a collections/workflow from DynamoDB"""
    items_page = deployment.get_workflow_items(
        collections,
        workflow_name,
        state,
        since,
        limit,
        nextkey,
        sort_ascending,
        sort_index,
    )
    click.echo(json.dumps(items_page, indent=2))


@manage.command("get-workflow-item")
@click.argument("collections")
@click.argument("workflow_name")
@click.argument("itemid")
@pass_deployment
def get_workflow_item(
    deployment: Deployment,
    collections: str,
    workflow_name: str,
    itemid: str,
):
    """Get individual item for a collections/workflow from DynamoDB"""
    result = deployment.get_workflow_item(
        collections,
        workflow_name,
        itemid,
    )
    click.echo(json.dumps(result, indent=2))
