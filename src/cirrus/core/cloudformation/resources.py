from copy import deepcopy

from .base import BaseCFObject


JOB_DEFINITION_TYPE = 'AWS::Batch::JobDefinition'


def convert_env_to_batch_env(env):
    if not env:
        return []
    for name, val in env.items():
        yield {'Name': name, 'Value': val}


def convert_batch_env_to_env(env):
    _env = {}
    for item in env:
        _env[item['Name']] = item['Value']
    return _env


class Resource(BaseCFObject):
    top_level_key = 'Resources'
    task_batch_resource_attr = 'batch_resources'

    def __new__(cls, name, definition, *args, **kwargs):
        resource_type = definition.get('Type')

        if resource_type == JOB_DEFINITION_TYPE:
            cls = JobDefinition

        self = super().__new__(cls)
        self.resource_type = resource_type

        return self


class JobDefinition(Resource):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.parent_component and self.parent_component.batch_env:
            self.update_environment(self.parent_component.batch_env)

    def update_environment(self, env):
        item = self.definition
        keys = ['Properties', 'ContainerProperties']

        for key in keys:
            if key not in item:
                item[key] = {}
            item = item[key]

        try:
            _env = item['Environment']
        except KeyError:
            item['Environment'] = env
        else:
            # prefers the env vars set in the batch env
            # over those inherited from the task env config
            update_env = deepcopy(env)
            update_env.update(convert_batch_env_to_env(_env))
            item['Environment'] = list(convert_env_to_batch_env(update_env))
