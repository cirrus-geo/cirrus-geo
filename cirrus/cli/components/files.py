import logging

from rich.markdown import Markdown

from .base.file import ComponentFile


logger = logging.getLogger(__name__)


default_readme = '''#{name}

Fill in this README with details for this {type}

## Description

It is often best to tell people what this {type}
does. And perhaps why they might choose to use it.

## Configuration Parameters

It's not uncommon to list out the parameters so people can better
understand how to use this {type} once they have chosen to do so.
Don't just say what they are, but where they go.

Configuration parameters are passed in `payload['process']['tasks']['copy-metadata']`:

- Name: `mappings`
  Type: `dict`
  Required: True
  Default: None
  An array of mapping dicts that define source item,
  destination item, and metadata fields to copy


Providing an example is often best.

Example:
```
"copy-metadata": {{
  "mappings":[
    {{
      "source": "GEO",
      "destination": "SLC",
      "metadata": {{
        "assets": ["preview", "thumbnail"]
      }}
    }}
  ]
}}
```

## Detail any other options

It's possible your {type} uses more fields to define options.

Maybe your {type} also REQUIRES the following parameters
supplied in `payload['process']['item-queries']`:

```
"item-queries": {{
  "GEO": {{
    "sar:product_type": "GEO"
    }},
  "SLC": {{
    "sar:product_type": "SLC"
    }},
  "SICD": {{
    "sar:product_type": "SICD"
  }}
}}
```
'''.format


default_handler = '''#!/usr/bin/env python
from cirruslib import Catalog, get_task_logger


def handler(payload, context={{}}):
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger(f"{{__name__}}.{name}", catalog=catalog)
    return catalog
'''.format


# TODO: figure out most basic permissions
default_lambda_def = '''description: 'fill in a description here'
memorySize: 128
timeout: 60
iamRoleStatements: []
python_requirements: []
'''


default_workflow = '''name: ${{self:service}}-${{self:provider.stage}}-{name}
definition:
  Comment: add a descripton here then fill in the workflow states
  StartAt: publish
  States:
    publish:
      Type: Task
      Resource:
        Fn::GetAtt: [publish, Arn]
      End: True
      Retry:
        - ErrorEquals: ["Lambda.TooManyRequestsException", "Lambda.Unknown"]
          IntervalSeconds: 1
          BackoffRate: 2.0
          MaxAttempts: 5
      Catch:
        - ErrorEquals: ["States.ALL"]
          ResultPath: $.error
          Next: workflow-failed
    workflow-failed:
      Type: Task
      Resource:
        Fn::GetAtt: [workflow-failed, Arn]
      Retry:
        - ErrorEquals: ["Lambda.TooManyRequestsException", "Lambda.Unknown"]
          IntervalSeconds: 1
          BackoffRate: 2.0
          MaxAttempts: 5
      Next: failure
    failure:
      Type: Fail
'''.format


class Readme(ComponentFile):
    def __init__(self, *args, name='README.md', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        return default_readme(
            name=component.name,
            type=component.component_type,
        )

    def show(self):
        if self.content is None:
            logger.error(
                "%s '%s' has no README.",
                self.parent.component_type.capitalize(),
                self.parent.name
            )
            return
        self.console.print(Markdown(self.content))


class PythonHandler(ComponentFile):
    def __init__(self, *args, name='task.py', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        return default_handler(name=component.name)


class LambdaDefinition(ComponentFile):
    def __init__(self, *args, name='definition.yml', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        from cirrus.cli.utils import yaml
        return yaml.NamedYamlable(default_lambda_def).to_yaml()


class StepFunctionDefinition(ComponentFile):
    def __init__(self, *args, name='definition.yml', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        from cirrus.cli.utils import yaml
        return yaml.NamedYamlable(default_workflow(name=component.name)).to_yaml()
