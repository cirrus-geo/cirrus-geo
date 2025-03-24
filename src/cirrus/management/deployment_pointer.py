from __future__ import annotations

import json

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

import boto3

from botocore.exceptions import ClientError

from cirrus.lib.utils import get_client
from cirrus.management.exceptions import DeploymentNotFoundError, MissingParameterError

DEPLOYMENTS_PREFIX = "/cirrus/deployments/"

# core required vars.  Not exclusive.
REQUIRED_VARS = {
    "CIRRUS_PAYLOAD_BUCKET",
    "CIRRUS_BASE_WORKFLOW_ARN",
    "CIRRUS_PROCESS_QUEUE_URL",
    "CIRRUS_STATE_DB",
    "CIRRUS_PREFIX",
}


class PointerType(StrEnum):
    ParamStore = "parameter_store"


def get_parameters_by_path(
    path: str,
    session: boto3.Session | None = None,
) -> Iterator[dict[str, Any]]:
    ssm = get_client("ssm", session=session)
    next_token = ""

    while True:
        resp = ssm.get_parameters_by_path(
            Path=path,
            Recursive=True,
            NextToken=next_token,
        )

        yield from resp["Parameters"]
        next_token = resp.get("NextToken", "")

        if next_token == "":
            break


@dataclass()
class Pointer:
    _type: PointerType
    value: str

    @classmethod
    def from_string(cls: type[Self], string: str) -> Self:
        obj = json.loads(string)
        obj["_type"] = obj.pop("type")

        return cls(**obj)

    def resolve(self):
        match self._type:
            case PointerType.ParamStore:
                return ParamStoreDeployment(self.value)
            case _ as unknown:
                raise TypeError(f"Unsupported pointer type '{unknown}'")


class ParamStoreDeployment:
    def __init__(self, deployment_key: str):
        self.prefix = deployment_key

    def fetch(self, session=boto3.Session) -> dict[str, str]:
        """Get all parameters for specific deployment"""

        return {
            param["Name"].removeprefix(self.prefix): param["Value"]
            for param in get_parameters_by_path(self.prefix, session)
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
    def get_pointer(
        cls,
        deployment_name: str,
        region: str | None = None,
        session: boto3.Session | None = None,
    ):
        """Get pointer to deployment in param store.  Pointer is one param"""
        ssm = get_client("ssm", region=region, session=session)
        try:
            parameter = ssm.get_parameter(
                Name=f"{DEPLOYMENTS_PREFIX}{deployment_name}",
            )["Parameter"]
            return cls._from_parameter(parameter, name=deployment_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                raise DeploymentNotFoundError(deployment_name) from e
            raise

    @staticmethod
    def list_deployments(
        session: boto3.Session,
    ) -> Iterator[str]:
        """Retrieve and list names of available deployments in parameter
        store"""

        yield from (
            param["Name"].removeprefix(DEPLOYMENTS_PREFIX)
            for param in get_parameters_by_path(DEPLOYMENTS_PREFIX, session=session)
        )

    @staticmethod
    def validate_vars(environment: dict[str, str]):
        missing = REQUIRED_VARS - set(environment.keys())
        if missing:
            raise MissingParameterError(*missing)
        return environment

    def get_environment(
        self,
        session: boto3.Session,
    ) -> dict[str, str]:
        """Get env vars for single named deployment"""

        return self.validate_vars(self.pointer.resolve().fetch(session=session))
