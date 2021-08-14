import logging

from rich.markdown import Markdown

from .file_base import ComponentFile


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
"copy-metadata": {
  "mappings":[
    {
      "source":"GEO",
      "destination":"SLC",
      "metadata":{
        "assets": ["preview", "thumbnail"]
      }
    }
  ]
}
```

## Detail any other options

It's possible your {type} uses more fields to define options.

Maybe your {type} also REQUIRES the following parameters
supplied in `payload['process']['item-queries']`:

```
"item-queries": {
  "GEO":{
    "sar:product_type": "GEO"
    },
  "SLC":{
    "sar:product_type": "SLC"
    },
  "SICD":{
    "sar:product_type": "SICD"
  }
}
```
'''.format


default_lambda = '''#!/usr/bin/env python
from cirruslib import Catalog, get_task_logger


def handler(payload, context={{})}:
    catalog = Catalog.from_payload(payload)
    logger = get_task_logger(f"{{__name__}}.{name}", catalog=catalog)
    return catalog
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


class Python(ComponentFile):
    def __init__(self, *args, name='task.py', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        return default_lambda(name=component.name)


class Definition(ComponentFile):
    def __init__(self, *args, name='definition.yml', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        import json
        return json.dumps({
            'description': '',
            'memorySize': 128,
            'timeout': 60,
            # TODO: figure out most basic permissions
            'iamRoleStatements': [],
            'python_requirements': [],
        })
