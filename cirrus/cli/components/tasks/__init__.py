import textwrap

import click

from ..base import Lambda
from .. import files
from cirrus.cli.resources import TaskResource


JOB_DEFINITION_TYPE = 'AWS::Batch::JobDefinition'


def convert_env_to_batch_env(env):
    for name, val in env.items():
        yield {'Name': name, 'Value': val}


def convert_batch_env_to_env(env):
    _env = {}
    for item in env:
        _env[item['Name']] = item['Value']
    return _env


# TODO: move this into a method on the TaskResource so we can call it from config register
# load env into JobDefn.Properties.ContainerProperties.Environment
def update_job_env(job, env):
    item = job
    keys = ['Properties', 'ContainerProperties']

    for key in keys:
        if not key in item:
            item[key] = {}
        item = item[key]

    try:
        _env = item['Environment']
    except KeyError:
        item['Environment'] = env
    else:
        # prefers the env vars set in the batch env
        # over those inherited from the task env config
        item['Environment'] = list(convert_env_to_batch_env(
            env.update(convert_batch_env_to_env(_env)),
        ))


class Task(Lambda):
    # handler is special on tasks, as it is not required if lambda is disabled
    # we do a bit of extra validation for this in the load_config method
    handler = files.PythonHandler(optional=True)

    def load_config(self):
        super().load_config()

        if self.lambda_enabled:
            self.handler.validate(required=True)

        # global env vars from cirrus.yml inherited in config build step
        self.batch_env = self.config.get('environment', {})
        batch = self.config.get('batch', {})
        self.batch_enabled = batch.get('enabled', True) and self._enabled and bool(batch)
        self.batch_resources = [
            self.create_batch_resource(name, definition)
            for name, definition in batch.get('resources', {}).items()
        ]

    def create_batch_resource(self, name, definition):
        resource = TaskResource(self, name, definition, self.definition.path)

        if resource.resource_type == JOB_DEFINITION_TYPE and self.batch_env:
            update_job_env(resource.definition, self.batch_env)

        return resource

    def display_attrs(self):
        yield from super().display_attrs()
        if self.lambda_enabled:
            yield 'lambda'
        if self.batch_enabled:
            yield 'batch'

    def detail_display(self):
        super().detail_display()
        click.echo(f'Batch enabled: {self.batch_enabled}')
        if not self.batch_resources:
            return
        click.echo(f'Batch resources:')
        for resource in self.batch_resources:
            click.echo("  {}:\n{}".format(
                click.style(resource.name, fg='yellow'),
                textwrap.indent(
                    resource.definition.to_yaml(),
                    '    ',
                ),
            ))
