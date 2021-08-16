from .. import files
from ..base import Lambda


class CoreTask(Lambda):
    enable_cli = False
    user_extendable = False
    display_type = 'Core Task'

    python = files.Python()
    definition = files.Definition()
    # make this not optional once we have them
    readme = files.Readme(optional=True)
