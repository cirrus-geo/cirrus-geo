from cirrus.cli.component import Lambda, files


class CoreTask(Lambda):
    enable_cli = False
    user_extendable = False

    python = files.Python()
    definition = files.Definition()
    # make this not optional once we have them
    readme = files.Readme(optional=True)
