from .base import StepFunction
from .files import ComponentFile


class Workflow(StepFunction):
    test_payload = ComponentFile(name="test-payload.json", optional=True)
