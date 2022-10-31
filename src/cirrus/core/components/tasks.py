import textwrap

import click

from cirrus.core.cloudformation import CFObject

from .base import Lambda


class Task(Lambda):
    def load_config(self):
        super().load_config()

        batch = self.config.get("batch", {})
        self.batch_enabled = (
            batch.get("enabled", True) and self._enabled and bool(batch)
        )
        self.batch_cloudformation = [
            cf_object
            for top_level_key, cf_items in batch.get("resources", {}).items()
            for cf_object in CFObject.create_cf_objects(
                self.definition.path,
                top_level_key,
                cf_items,
                parent_component=self,
            )
        ]

    def display_attrs(self):
        yield from super().display_attrs()
        if self.lambda_enabled:
            yield "lambda"
        if self.batch_enabled:
            yield "batch"

    def detail_display(self):
        super().detail_display()
        click.echo(f"Batch enabled: {self.batch_enabled}")
        if not self.batch_cloudformation:
            return
        click.echo("Batch resources:")
        for resource in self.batch_cloudformation:
            click.echo(
                "  {}:\n{}".format(
                    click.style(resource.name, fg="yellow"),
                    textwrap.indent(
                        resource.definition.to_yaml(),
                        "    ",
                    ),
                )
            )

    @classmethod
    def extra_create_args(cls):
        def wrapper(func):
            return click.option(
                "-t",
                "--type",
                "task_types",
                type=click.Choice(["batch", "lambda"]),
                multiple=True,
                required=True,
            )(func)

        return wrapper

    @classmethod
    def create(cls, name: str, description: str, task_types):
        new = cls._create_init(name, description)
        new.batch_enabled = "batch" in task_types
        new.lambda_enabled = "lambda" in task_types
        new._create_do()
        return new

    def _load(self, init_files=False):
        if init_files and not self.lambda_enabled:
            del self.files["handler"]
        super()._load(init_files=init_files)
