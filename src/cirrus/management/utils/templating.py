import logging

from collections import ChainMap
from collections.abc import Mapping, MutableMapping
from string import Template
from typing import Any

logger = logging.getLogger(__name__)


class DefaultableTemplate(Template):
    # pattern is compiled to a regex by Template metaclass
    # Note this pattern works for any default value _except_
    # those with a `}` in them. To accommodate such defaults
    # would require a significantly more complex implementation.
    # We will be better off switching to a real templating solution
    # if that becomes a need.
    pattern = r"""
    \$(?:
      (?P<escaped>\$)
      | (?P<named>[_a-z][_a-z0-9]*)
      | {(?P<braced>[_a-z][_a-z0-9]*(?:\?[^}]*)?)}
      | (?P<invalid>)
    )
    """  # type: ignore

    def handle_defaults(self, *args, **kwargs) -> Mapping[str, Any]:
        mapping: MutableMapping[str, Any]

        if len(args) > 1:
            raise TypeError("Too many positional arguments")
        if not args:
            mapping = kwargs
        elif kwargs:
            mapping = ChainMap(kwargs, args[0])
        else:
            mapping = args[0]

        # pattern is not a str, but a compile regex per metaclass
        for val in self.pattern.findall(self.template):  # type: ignore
            if not val[2]:
                continue

            match = val[2]

            key, *default = match.split("?", 1)

            if default:
                mapping[match] = mapping.get(key, default[0])

        return mapping

    def substitute(self, *args, **kwargs) -> str:
        return super().substitute(self.handle_defaults(*args, **kwargs))

    def safe_substitute(self, *args, **kwargs) -> str:
        return super().safe_substitute(self.handle_defaults(*args, **kwargs))


def template_payload(
    template: str,
    mapping: dict[str, str],
    silence_templating_errors=False,
    **kwargs,
):
    logger.debug("Templating vars: %s", mapping)
    template_fn = "safe_substitute" if silence_templating_errors else "substitute"
    return getattr(DefaultableTemplate(template), template_fn)(mapping, **kwargs)
