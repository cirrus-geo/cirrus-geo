from enum import Enum, unique


@unique
class StateEnum(str, Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    ABORTED = "ABORTED"

    def __str__(self):
        return self.value
