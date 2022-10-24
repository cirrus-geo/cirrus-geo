from copy import deepcopy

from .base import BaseCFObject

JOB_DEFINITION_TYPE = "AWS::Batch::JobDefinition"


def convert_env_to_batch_env(env):
    if not env:
        return []
    for name, val in env.items():
        yield {"Name": name, "Value": val}


def convert_batch_env_to_env(env):
    _env = {}
    for item in env or []:
        _env[item["Name"]] = item["Value"]
    return _env


class Resource(BaseCFObject):
    top_level_key = "Resources"
    task_batch_resource_attr = "batch_resources"

    def __new__(cls, name, definition, *args, **kwargs):
        resource_type = definition.get("Type")

        if resource_type == JOB_DEFINITION_TYPE:
            cls = JobDefinition

        self = super().__new__(cls)
        self.resource_type = resource_type

        return self


class JobDefinition(Resource):
    default_batch_env = {
        "AWS_DEFAULT_REGION": "#{AWS::Region}",
        "AWS_REGION": "#{AWS::Region}",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        inherit_env = None
        if self.parent_component:
            # we have a task parent and should use its env
            inherit_env = self.parent_component.environment
        elif self.project and self.project.config:
            # this a job def unassociated with a task and
            # we should use the global environment vars
            inherit_env = self.project.config.provider.environment
        self.update_environment(inherit_env)

    def update_environment(self, env):
        if not env:
            return

        # add default batch env vars to inherited env
        update_env = deepcopy(env)
        update_env.update(self.default_batch_env)

        # default job defn keys above Environment, if needed
        item = self.definition
        keys = ["Properties", "ContainerProperties"]
        for key in keys:
            if key not in item:
                item[key] = {}
            item = item[key]

        _env = item.get("Environment", {})
        update_env.update(convert_batch_env_to_env(_env))
        item["Environment"] = list(convert_env_to_batch_env(update_env))
