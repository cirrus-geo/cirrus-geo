from stactask.payload import Payload


class CirrusPayload(Payload):
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

        if "workflow-" not in self["id"]:
            raise ValueError(
                f"Payload 'id' field must contain 'workflow-': {self['id']}",
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
