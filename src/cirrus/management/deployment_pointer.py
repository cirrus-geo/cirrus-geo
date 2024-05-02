from __future__ import annotations

import json
import re

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any, Protocol, Self

import boto3

from cirrus.lib.utils import get_client

DEFAULT_CIRRUS_DEPLOYMENT_PREFIX = "/cirrus/deployments/"


def get_secret(
    secret_arn: str,
    region: str | None = None,
    session: boto3.Session | None = None,
) -> str:
    sm = get_client("secretsmanager", region=region, session=session)
    resp = sm.get_secret_value(
        SecretId=secret_arn,
    )
    return resp["SecretString"]


class PointerObject(Protocol):  # pragma: no cover
    account_id: str
    region: str

    @classmethod
    def from_string(cls: type[Self], string: str) -> Self: ...

    def fetch(
        self: Self,
        session: boto3.Session | None = None,
    ) -> str: ...


class SecretArn:
    _format = "arn:aws:secretsmanager:{region}:{account_id}:secret:{name}".format
    _regex = re.compile(
        r"^arn:aws:secretsmanager:(?P<region>[a-z0-9\-]+):(?P<account_id>\d{12}):secret:(?P<name>.+)$",
    )

    def __init__(self, account_id: str, region: str, name: str) -> None:
        self.account_id = account_id
        self.region = region
        self.name = name

    def __str__(self) -> str:
        return self._format(
            region=self.region,
            account_id=self.account_id,
            name=self.name,
        )

    @classmethod
    def from_string(cls, string: str) -> Self:
        match = cls._regex.match(string)

        if not match:
            raise ValueError(f"Unparsable secret arn string '{string}'")

        groups = match.groupdict()

        return cls(
            account_id=groups["account_id"],
            name=groups["name"],
            region=groups["region"],
        )

    def fetch(
        self,
        session: boto3.Session | None = None,
    ) -> str:
        return get_secret(
            secret_arn=str(self),
            region=self.region,
            session=session,
        )


class PointerType(StrEnum):
    SECRET = auto()


@dataclass()
class Pointer:
    _type: PointerType
    value: str

    @classmethod
    def from_string(cls: type[Self], string: str) -> Self:
        obj = json.loads(string)
        obj["_type"] = obj.pop("type")
        return cls(**obj)

    def resolve(self) -> PointerObject:
        match self._type:
            case PointerType.SECRET:
                return SecretArn.from_string(self.value)
            case _ as unknown:
                raise TypeError(f"Unsupported pointer type '{unknown}'")


@dataclass
class DeploymentPointer:
    prefix: str
    name: str
    pointer: Pointer

    @classmethod
    def _from_parameter(
        cls,
        parameter: dict[str, Any],
        prefix: str = "",
    ) -> DeploymentPointer:
        name = parameter["Name"][len(prefix) :]
        return cls(
            name=name,
            pointer=Pointer.from_string(parameter["Value"]),
            prefix=prefix,
        )

    @classmethod
    def get(
        cls,
        deployment_name: str,
        deployment_prefix: str = DEFAULT_CIRRUS_DEPLOYMENT_PREFIX,
        region: str | None = None,
        session: boto3.Session | None = None,
    ):
        ssm = get_client("ssm", region=region, session=session)
        return cls._from_parameter(
            ssm.get_parameter(
                Name=f"{deployment_prefix}{deployment_name}",
            )["Parameter"],
            prefix=deployment_prefix,
        )

    @classmethod
    def list(
        cls,
        deployment_prefix: str = DEFAULT_CIRRUS_DEPLOYMENT_PREFIX,
        region: str | None = None,
        session: boto3.Session | None = None,
    ) -> Iterator[DeploymentPointer]:
        ssm = get_client("ssm", region=region, session=session)
        resp = ssm.get_parameters_by_path(Path=deployment_prefix)
        for param in resp["Parameters"]:
            yield cls._from_parameter(
                param,
                prefix=deployment_prefix,
            )

    def get_config(
        self,
        session: boto3.Session | None = None,
    ) -> dict[str, Any]:
        return json.loads(self.pointer.resolve().fetch(session=session))
