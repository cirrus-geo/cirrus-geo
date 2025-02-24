from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Self

import boto3

from cirrus.lib.utils import get_client

PARAMETER_PREFIX = "/cirrus/deployments/"


@dataclass
class DeploymentEnvVars:
    # core required for built in
    dynamo_db: str
    payload_bucket: str
    process_sqs: str
    workflow_topic: str


# could be more outside of that for a given deployment for customization


@dataclass
class DeploymentPointer:
    prefix: str
    name: str
    environment: dict
    """
    Contains all related AWS pieces of a single cirrus deployment
    """

    @classmethod
    def _get_deployments(
        cls,
        prefix: str,
        name: str | None = None,
        region: str | None = None,
        session: boto3.Session | None = None,
    ) -> list[Self]:
        if name:  # if searching by name
            prefix = prefix + f"{name}"
        ssm = get_client("ssm", region=region, session=session)
        resp = ssm.get_parameters_by_path(
            Path=prefix,
            Recursive=True,
        )
        # TODO: handle pagination
        return cls.parse_deployments(resp)

    @classmethod
    def parse_deployments(
        cls,
        response: dict,
        prefix: str = PARAMETER_PREFIX,
    ) -> list[Self]:
        """
        Parse parameter response and return all deployments

        Parameter store entires shuld have format {prefix}{deployment_name}{component}
        """
        parameters = [
            cls.parsed_parameter(param, prefix) for param in response["Parameters"]
        ]
        deployment_names = sorted(
            {deployment_name for _, _, deployment_name in parameters},
        )

        return [
            cls(
                prefix,
                name,
                cls.cirrus_components(parameters, name),
            )
            for name in deployment_names
        ]

    @classmethod
    def get_deployment_by_name(
        cls,
        deployment_name: str,
        deployment_prefix: str = PARAMETER_PREFIX,
        region: str | None = None,
        session: boto3.Session | None = None,
    ):
        """
        Retrieve a single deployment configuration by name from parameter store
        """
        deployment = cls._get_deployments(
            deployment_prefix,
            deployment_name,
            region,
            session,
        )
        if deployment:
            return deployment[0]
        return None

    @classmethod
    def list_deployments(
        cls,
        deployment_prefix: str = PARAMETER_PREFIX,
        region: str | None = None,
        session: boto3.Session | None = None,
    ) -> Iterator[DeploymentPointer]:
        """Retrieve and list all deployments in parameter store"""
        yield from cls._get_deployments(
            deployment_prefix,
            region=region,
            session=session,
        )

    @classmethod
    def parsed_parameter(cls, param: dict, prefix: str) -> tuple[str, str, str]:
        """split param into name, value, and deployment name components"""
        return (
            param["Name"].split("/")[-1],
            param["Value"],
            param["Name"][len(prefix) : param["Name"].rindex("/")],
        )

    @classmethod
    def cirrus_components(
        cls,
        parameters: list[tuple[str, str, str]],
        name: str,
    ) -> dict[str, str]:
        return {
            param_name: value
            for param_name, value, deployment_name in parameters
            if deployment_name == name
        }
