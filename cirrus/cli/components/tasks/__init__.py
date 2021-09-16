import textwrap

import click

from ..base import Lambda
from cirrus.cli.resources import TaskResource


class Task(Lambda):
    def load_config(self):
        super().load_config()
        batch = self.config.pop('batch', {})
        self.batch_enabled = batch.get('Enabled', False)
        self.batch_resources = [
            TaskResource(self, name, definition, self.definition.path)
            for name, definition in batch.get('Resources', {}).items()
        ]

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
