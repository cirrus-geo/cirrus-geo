import logging

from .base import ComponentFile


logger = logging.getLogger(__name__)


# TODO: figure out most basic permissions
default_lambda = '''description: 'fill in a description here'
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


class BaseDefinition(ComponentFile):
    def __init__(self, *args, name='definition.yml', **kwargs):
        super().__init__(*args, name=name, **kwargs)

    @staticmethod
    def content_fn(component) -> str:
        return ''


class LambdaDefinition(BaseDefinition):
    @staticmethod
    def content_fn(component) -> str:
        return default_lambda


class StepFunctionDefinition(BaseDefinition):
    @staticmethod
    def content_fn(component) -> str:
        return default_workflow(name=component.name)
