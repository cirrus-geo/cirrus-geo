class CirrusError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class PayloadNotFoundError(CirrusError):
    def __init__(self, payload_id, *args, **kwargs) -> None:
        msg = f"Payload not found: {payload_id}"
        super().__init__(msg, *args, **kwargs)


class ExecutionNotFoundError(CirrusError):
    def __init__(self, payload_id, *args, **kwargs) -> None:
        msg = f"Execution not found for payload: {payload_id}"
        super().__init__(msg, *args, **kwargs)
