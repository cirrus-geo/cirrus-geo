from cirrus.exceptions import CirrusError


class SSOError(CirrusError):
    pass


class DeploymentConfigurationError(CirrusError):
    pass


class DeploymentNotFoundError(CirrusError):
    def __init__(self, deployment_name, *args, **kwargs):
        msg = f"Deployment not found: {deployment_name}"
        super().__init__(msg, *args, **kwargs)


class PayloadNotFoundError(CirrusError):
    def __init__(self, payload_id, *args, **kwargs):
        msg = f"Payload not found: {payload_id}"
        super().__init__(msg, *args, **kwargs)


class NoExecutionsError(CirrusError):
    def __init__(self, payload_id, *args, **kwargs):
        msg = f"Payload has no executions: {payload_id}"
        super().__init__(msg, *args, **kwargs)
