import textwrap

import click

from ..base import Lambda
from cirrus.cli.resources import TaskResource


JOB_DEFINITION_TYPE = 'AWS::Batch::JobDefinition'


def convert_lambda_env_to_batch_env(env):
    for name, val in env.items():
        yield {'Name': name, 'Value': val}


def set_nested_value_if_unset(_dict, value, *keys):
    for key in keys[:-1]:
        if key not in _dict:
            _dict[key] = {}
        elif not hasattr(_dict[key], '__getitem__'):
            raise RuntimeError(
                f"Key {key} already set on object and value not dict-like",
            )
        _dict = _dict[key]

    key = keys[-1]
    if key not in _dict:
        _dict[key] = value


class Task(Lambda):
    def load_config(self):
        super().load_config()
        self.batch_env = list(convert_lambda_env_to_batch_env(
            self.config.get('environment', {}),
        ))
        batch = self.config.get('batch', {})
        self.batch_enabled = batch.get('enabled', True) and self.enabled
        self.batch_resources = [
            self.create_batch_resource(name, definition)
            for name, definition in batch.get('resources', {}).items()
        ]

    def create_batch_resource(self, name, definition):
        resource = TaskResource(self, name, definition, self.definition.path)

        if resource.type != JOB_DEFINITION_TYPE:
            return resource

        # load env into JobDefn.Properties.ContainerProperties.Environment
        if self.batch_env:
            set_nested_value_if_unset(
                resource.definition,
                self.batch_env,
                'Properties',
                'ContainerProperties',
                'Environment',
            )

        return resource

    def detail_display(self):
        super().detail_display()
        click.echo(f'\nBatch Enabled: {self.batch_enabled}')
        click.echo(f'Batch resources:')
        for resource in self.batch_resources:
            click.echo("  {}:\n{}".format(
                click.style(resource.name, fg='yellow'),
                textwrap.indent(
                    resource.definition.to_yaml(),
                    '    ',
                ),
            ))
