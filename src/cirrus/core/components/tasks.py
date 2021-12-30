import textwrap
import click

from .base import Lambda
from . import files
from cirrus.core.cloudformation import CFObject


class Task(Lambda):
    # handler is special on tasks, as it is not required if lambda is disabled
    # we do a bit of extra validation for this in the load_config method
    handler = files.PythonHandler(optional=True)

    def load_config(self):
        super().load_config()

        if self.lambda_enabled:
            self.handler.validate(required=True)

        batch = self.config.get('batch', {})
        self.batch_enabled = batch.get('enabled', True) and self._enabled and bool(batch)
        self.batch_cloudformation = [
            cf_object
            for top_level_key, cf_items in batch.get('resources', {}).items()
            for cf_object in CFObject.create_cf_objects(
                self.definition.path,
                top_level_key,
                cf_items,
                is_builtin=self.is_core_component,
                parent_component=self,
            )
        ]

    def display_attrs(self):
        yield from super().display_attrs()
        if self.lambda_enabled:
            yield 'lambda'
        if self.batch_enabled:
            yield 'batch'

    def detail_display(self):
        super().detail_display()
        click.echo(f'Batch enabled: {self.batch_enabled}')
        if not self.batch_cloudformation:
            return
        click.echo('Batch resources:')
        for resource in self.batch_cloudformation:
            click.echo("  {}:\n{}".format(
                click.style(resource.name, fg='yellow'),
                textwrap.indent(
                    resource.definition.to_yaml(),
                    '    ',
                ),
            ))

    @classmethod
    def extra_create_args(cls):
        def wrapper(func):
            return click.option('--has-batch/--no-batch', default=False)(
                click.option('--has-lambda/--no-lambda', default=True)(
                    func,
                ),
            )
        return wrapper

    @classmethod
    def create(cls, name: str, description: str, has_batch: bool, has_lambda: bool):
        new = cls._create_init(name, description)
        new.lambda_enabled = has_lambda
        new.batch_enabled = has_batch
        new._create_do()
        return new
