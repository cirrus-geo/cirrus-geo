from __future__ import annotations

import contextlib
import json

import stactask

from cirrus.lib.errors import NoUrlError
from cirrus.lib.utils import PAYLOAD_ID_REGEX, extract_event_records, payload_from_s3


class CirrusPayload(stactask.payload.Payload):
    """Extends stac-task Payload with Cirrus-specific validation and ID setting."""

    def __init__(self, *args, set_id_if_missing: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if "id" not in self and set_id_if_missing:
            self.set_id()

    def validate(self) -> None:
        super().validate()

        if "process" not in self:
            raise ValueError(
                "Payload must contain a 'process' array of process definitions",
            )

        if not isinstance(self["process"], list) or len(self["process"]) == 0:
            raise TypeError(
                "Payload 'process' field must be an array "
                "with at least one process definition",
            )

        if "workflow" not in self.process_definition:
            raise ValueError(
                "Payload must contain a 'workflow' field specifying the workflow name",
            )

        if not PAYLOAD_ID_REGEX.match(self["id"]):
            raise ValueError(
                "Payload 'id' field must match '${COLLECTIONS}/"
                f"workflow-${{WORKFLOW_NAME}}/${{ITEMIDS}}: {self['id']}",
            )

    def set_id(self) -> None:
        if "id" in self:
            return

        if not self.items_as_dicts:
            raise ValueError(
                "Payload has no 'id' specified and one "
                "cannot be constructed without 'features'.",
            )

        if "workflow" not in self.process_definition:
            raise ValueError(
                "Payload has no 'id' specified and one cannot be "
                "constructed without 'workflow' in the process definition.",
            )

        if "collections" in self.process_definition:
            # allow overriding of collections name
            collections_str = self.process_definition["collections"]
        else:
            # otherwise, get from items
            cols = sorted(
                {i["collection"] for i in self.items_as_dicts if "collection" in i},
            )
            collections_str = "/".join(cols) if len(cols) != 0 else "none"

        items_str = "/".join(sorted([i["id"] for i in self.items_as_dicts]))
        self["id"] = (
            f"{collections_str}/workflow-{self.process_definition['workflow']}/{items_str}"
        )

    @classmethod
    def from_event(cls, event: dict, **kwargs) -> CirrusPayload:
        """Parse a Cirrus event and return a CirrusPayload instance

        Args:
            event (Dict): An event from SNS, SQS, or containing an s3 URL to payload

        Returns:
            CirrusPayload: A CirrusPayload instance
        """
        records = list(extract_event_records(event))

        if len(records) == 0:
            raise ValueError("Failed to extract record: %s", json.dumps(event))
        if len(records) > 1:
            raise ValueError("Multiple payloads are not supported")

        payload = records[0]

        # if the payload has a URL in it then we'll fetch it from S3
        with contextlib.suppress(NoUrlError):
            payload = payload_from_s3(payload)

        return cls(payload, **kwargs)
