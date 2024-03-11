from enum import Enum, unique


@unique
class StateEnum(str, Enum):
    """Cirrus state strings"""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    ABORTED = "ABORTED"

    def __str__(self):
        return self.value


@unique
class SfnStatus(str, Enum):
    """StepFunctions status strings"""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    TIMED_OUT = "TIMED_OUT"
