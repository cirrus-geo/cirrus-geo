from enum import Enum, unique


@unique
class StateEnum(str, Enum):
    """Cirrus state strings"""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    ABORTED = "ABORTED"
    CLAIMED = "CLAIMED"

    def __str__(self):
        return self.value


@unique
class SfnStatus(str, Enum):
    """StepFunctions status strings"""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    TIMED_OUT = "TIMED_OUT"

    def __str__(self):
        return self.value


@unique
class WFEventType(str, Enum):
    """Cirrus Workflow Event Type strings"""

    CLAIMED_PROCESSING = "CLAIMED_PROCESSING"
    STARTED_PROCESSING = "STARTED_PROCESSING"
    ALREADY_INVALID = "ALREADY_INVALID"
    ALREADY_PROCESSING = "ALREADY_PROCESSING"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    DUPLICATE_ID_ENCOUNTERED = "DUPLICATE_ID_ENCOUNTERED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    SUCCEEDED = "SUCCEEDED"
    INVALID = "INVALID"
    ABORTED = "ABORTED"
    RECORD_EXTRACT_FAILED = "RECORD_EXTRACT_FAILED"
    NOT_A_PROCESS_PAYLOAD = "NOT_A_PROCESS_PAYLOAD"

    def __str__(self):
        return self.value
