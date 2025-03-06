from __future__ import annotations

import json

from dataclasses import dataclass
from typing import Any, Self

import boto3

from cirrus.lib.utils import get_client
from cirrus.management.exceptions import MissingParameterError

DEPLOYMENTS_PREFIX = "/cirrus/deployments/"

# core required vars.  Not exclusive.
REQUIRED_VARS = [
    "CIRRUS_PAYLOAD_BUCKET",
    "CIRRUS_BASE_WORKFLOW_ARN",
    "CIRRUS_PROCESS_QUEUE_URL",
    "CIRRUS_STATE_DB",
    "CIRRUS_PREFIX",
]


@dataclass()
class Pointer:
    _type: str
    value: str

    @classmethod
    def from_string(cls: type[Self], string: str) -> Self:
        obj = json.loads(string)
        obj["_type"] = obj.pop("type")

        return cls(**obj)

    def resolve(self):
        match self._type:
            case "parameter_store":
                return ParamStoreDeployment(self.value)
            case _ as unknown:
                raise TypeError(f"Unsupported pointer type '{unknown}'")


class ParamStoreDeployment:
    def __init__(self, deployment_key: str):
        self.prefix = deployment_key

    def fetch(self, session=boto3.Session) -> dict[str, str]:
        """Get all parameters for specific deployment"""

        parameters = DeploymentPointer._get_parameters(self.prefix, session)
        return {
            param["Name"].split(self.prefix)[1]: param["Value"] for param in parameters
        }


@dataclass
class DeploymentPointer:
    name: str
    pointer: Pointer
    """
    Class to retrieve deployment pointer and using pointer
    for building deployment
    """

    @classmethod
    def _from_parameter(
        cls,
        parameter: dict[str, Any],
        name: str = "",
    ) -> DeploymentPointer:
        return cls(
            name=name,
            pointer=Pointer.from_string(parameter["Value"]),
        )

    @classmethod
    def _get_parameters_by_path(cls, ssm, prefix: str, next: str = ""):
        return ssm.get_parameters_by_path(
            Path=prefix,
            Recursive=True,
            NextToken=next,
        )

    @classmethod
    def _get_parameters(
        cls,
        prefix: str,
        session: boto3.Session,
    ) -> list[dict[str, Any]]:
        ssm = get_client("ssm", region=session.region_name, session=session)
        resp = cls._get_parameters_by_path(ssm, prefix)
        parameters = resp["Parameters"]

        # handle pagination
        while "NextToken" in resp:
            resp = cls._get_parameters_by_path(ssm, prefix, resp["NextToken"])
            parameters = parameters + resp["Parameters"]

        return parameters

    @classmethod
    def get_pointer(
        cls,
        deployment_name: str,
        region: str | None = None,
        session: boto3.Session | None = None,
    ):
        """Get pointer to deployment in param store.  Pointer is one param"""
        ssm = get_client("ssm", region=region, session=session)
        return cls._from_parameter(
            ssm.get_parameter(Name=f"{DEPLOYMENTS_PREFIX}{deployment_name}")[
                "Parameter"
            ],
            name=deployment_name,
        )

    @classmethod
    def list_deployments(
        cls,
        session: boto3.Session,
    ) -> list[str]:
        """Retrieve and list names of available deployments in parameter
        store"""
        parameters = cls._get_parameters(
            DEPLOYMENTS_PREFIX,
            session=session,
        )

        return [param["Name"].split(DEPLOYMENTS_PREFIX)[1] for param in parameters]

    def validate_vars(self, environment: dict[str, str]):
        missing = [field for field in REQUIRED_VARS if field not in environment]
        if missing:
            raise MissingParameterError(", ".join(missing))
        return environment

    def get_environment(
        self,
        session: boto3.Session,
    ) -> dict[str, str]:
        """Get env vars for single named deployment"""

        return self.validate_vars(self.pointer.resolve().fetch(session=session))
