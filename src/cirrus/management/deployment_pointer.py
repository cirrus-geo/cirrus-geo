from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Self

import boto3

from cirrus.lib.utils import get_client

DEFAULT_CIRRUS_DEPLOYMENT_PREFIX = "/cirrus/deployments/"


@dataclass
class Components:
    process_lambda: str
    state_db_name: str
    payload_bucket: str
    dlq_queue_url: str | None
    process_topic: str | None
    process_queue_url: str | None


@dataclass
class DeploymentPointer:
    prefix: str
    name: str
    components: dict
    """
    Contains all related AWS pieces of a single cirrus deployment
    """

    @classmethod
    def _get_deployments(
        cls,
        prefix: str,
        region: str | None = None,
        session: boto3.Session | None = None,
    ) -> list[Self]:
        ssm = get_client("ssm", region=region, session=session)
        resp = ssm.get_parameters_by_path(
            Path=prefix,
            Recursive=True,
        )
        return cls.parse_deployments(resp, prefix)

    @classmethod
    def parse_deployments(cls, response: dict, prefix: str) -> list[Self]:
        """
        Parse parameter response and return all deployments

        Parameter store entires shuld have format {prefix}{deployment_name}{component}
        """

        # break parameter name into components
        parameters = [
            (
                param["Name"].split("/")[-1],
                param["Value"],
                param["Name"][len(prefix) : param["Name"].rindex("/") + 1],
            )
            for param in response["Parameters"]
        ]
        # name set
        deployment_names = {deployment_name for _, _, deployment_name in parameters}

        return [
            cls(
                prefix,
                name,
                {
                    param_name: value
                    for param_name, value, deployment_name in parameters
                    if deployment_name == name
                },
            )
            for name in deployment_names
        ]

    @classmethod
    def get(
        cls,
        deployment_name: str,
        deployment_prefix: str = DEFAULT_CIRRUS_DEPLOYMENT_PREFIX,
        region: str | None = None,
        session: boto3.Session | None = None,
    ):
        """
        Retrieve a single deployment configuration by name from parameter store
        """
        deployments = cls._get_deployments(deployment_prefix, region, session)
        for deployment in deployments:
            if deployment.name == deployment_name:
                return deployment
        return None

    @classmethod
    def list(
        cls,
        deployment_prefix: str = DEFAULT_CIRRUS_DEPLOYMENT_PREFIX,
        region: str | None = None,
        session: boto3.Session | None = None,
    ) -> Iterator[DeploymentPointer]:
        """Retrieve and list all deployments in parameter store"""
        yield from cls._get_deployments(deployment_prefix, region, session)
