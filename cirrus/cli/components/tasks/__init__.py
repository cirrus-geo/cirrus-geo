import textwrap
import click

from ..base import Lambda
from .. import files
from cirrus.cli.resources import Resource


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
        resource = Resource(name, definition, self.definition.path, parent_task=self)

        if self.batch_env and hasattr(resource, 'update_environment'):
            resource.update_environement(self.batch_env)

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
