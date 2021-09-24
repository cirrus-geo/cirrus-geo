from ..base import BaseResource


class Resource(BaseResource):
    top_level_key = 'Resources'
    task_batch_resource_attr = 'batch_resources'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.resource_type = self.definition.get('Type', '')

    @property
    def display_name(self):
        return '{}{} ({})'.format(
            self.name,
            f' [{self.resource_type}]' if self.resource_type else '',
            self.display_source,
        )


class TaskResource(Resource):
    def __init__(self, parent_task, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.parent_task = parent_task

    @property
    def display_source(self):
        built_in = 'built-in ' if self.parent_task.is_core_component else ''
        return f'from {built_in}task {self.parent_task.name}'
