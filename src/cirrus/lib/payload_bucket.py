import contextlib
import os
import uuid

from typing import Any

from boto3utils import s3

from cirrus.lib.errors import NoUrlError, UndefinedPayloadBucketError
from cirrus.lib.utils import payload_from_s3

PREFIX_ROOT = "cirrus"

PREFIX_TMP = f"{PREFIX_ROOT}/tmp"  # noqa: S108
PREFIX_BATCH = f"{PREFIX_TMP}/batch"
PREFIX_INVALID = f"{PREFIX_TMP}/invalid"
PREFIX_OVERSIZED = f"{PREFIX_TMP}/oversized"

PREFIX_EXECS = f"{PREFIX_ROOT}/executions"

INPUT_KEY = "input.json"
OUTPUT_KEY = "output.json"


class PayloadBucket:
    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name

    def name(self) -> str:
        if self._bucket_name:
            return self._bucket_name

        payload_bucket = os.getenv("CIRRUS_PAYLOAD_BUCKET")

        if not payload_bucket:
            raise UndefinedPayloadBucketError(
                "CIRRUS_PAYLOAD_BUCKET env var is not defined",
            )

        return payload_bucket

    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        parsed = s3.urlparse(url)
        return parsed["bucket"], parsed["key"]

    def _upload_payload(
        self,
        payload: dict[str, Any],
        key: str,
        prefix: str = "",
        copy_from_url: bool = True,
    ) -> str:
        """Helper function to upload a dict (not necessarily a payload) to s3"""
        if "url" in payload and not copy_from_url:
            # payload is already uploaded and we're not supposed to copy it
            return payload["url"]

        # if the payload has a URL in it then we'll fetch it from S3
        with contextlib.suppress(NoUrlError):
            payload = payload_from_s3(payload)

        prefix = prefix + "/" if prefix else prefix

        url = f"s3://{self.name()}/{prefix}{key}"
        s3().upload_json(payload, url)
        return url

    def upload_oversize_payload(
        self,
        payload: dict[str, Any],
    ) -> str:
        return self._upload_payload(
            payload=payload,
            key=f"{uuid.uuid1()}.json",
            prefix=PREFIX_OVERSIZED,
        )

    def upload_batch_payload(
        self,
        payload: dict[str, Any],
    ) -> str:
        return self._upload_payload(
            payload=payload,
            # ideally we'd use {uuid.uuid1()}/input.json but we keep this
            # format for backwards compatibility with the old cirrus.lib ways
            key=f"{payload['id']}/{uuid.uuid1()}.json",
            prefix=PREFIX_BATCH,
            # in the batch case if we already have a url then we can just use it
            copy_from_url=False,
        )

    def upload_invalid_payload(
        self,
        payload: dict[str, Any],
    ) -> str:
        return self._upload_payload(
            payload=payload,
            key=f"{uuid.uuid1()}.json",
            prefix=PREFIX_INVALID,
        )

    @classmethod
    def exec_payload_prefix(
        cls,
        payload_id: str,
        execution_id: str,
    ) -> str:
        return f"{PREFIX_EXECS}/{payload_id}/{execution_id}"

    def get_input_payload_url(
        self,
        payload_id: str,
        execution_id: str,
    ) -> str:
        prefix = self.exec_payload_prefix(payload_id, execution_id)
        return f"s3://{self.name()}/{prefix}/{INPUT_KEY}"

    def get_output_payload_url(
        self,
        payload_id: str,
        execution_id: str,
    ) -> str:
        prefix = self.exec_payload_prefix(payload_id, execution_id)
        return f"s3://{self.name()}/{prefix}/{OUTPUT_KEY}"

    def upload_input_payload(
        self,
        payload: dict[str, Any],
        payload_id: str,
        execution_id: str,
    ) -> str:
        return self._upload_payload(
            payload=payload,
            key=INPUT_KEY,
            prefix=self.exec_payload_prefix(payload_id, execution_id),
        )

    def upload_output_payload(
        self,
        payload: dict[str, Any],
        payload_id: str,
        execution_id: str,
    ) -> str:
        return self._upload_payload(
            payload=payload,
            key=OUTPUT_KEY,
            prefix=self.exec_payload_prefix(payload_id, execution_id),
        )
