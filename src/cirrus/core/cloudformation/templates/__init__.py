import importlib.resources as _ir

TEMPLATE_EXT = ".yml"


templates = {}
for resource in _ir.contents(__package__):
    if not resource.endswith(TEMPLATE_EXT):
        continue
    with _ir.path(__package__, resource) as path:
        templates[resource[: -len(TEMPLATE_EXT)]] = path


locals().update(templates)
