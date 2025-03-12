import logging

from string import Template

logger = logging.getLogger(__name__)


def template_payload(
    template: str,
    mapping: dict[str, str],
    silence_templating_errors=False,
    **kwargs,
):
    logger.debug("Templating vars: %s", mapping)
    template_fn = "safe_substitute" if silence_templating_errors else "substitute"
    return getattr(Template(template), template_fn)(mapping, **kwargs)
