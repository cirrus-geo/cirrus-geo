import boto3
import click

pass_session = click.make_pass_decorator(boto3.Session)


class AliasedShortMatchGroup(click.Group):
    def __init__(self, *args, **kwargs):
        self.aliases = kwargs.pop("aliases", [])
        super().__init__(*args, **kwargs)
        self._alias2cmd = {}
        self._cmd2aliases = {}

    # used by the plugin loader
    def add_command(self, cmd, *args, **kwargs):
        super().add_command(cmd, *args, **kwargs)
        if aliases := getattr(cmd, "aliases", None):
            self._cmd2aliases[cmd.name] = aliases
            for alias in aliases:
                self._alias2cmd[alias] = cmd.name

    def command(self, *args, **kwargs):
        return self._register("command", *args, **kwargs)

    def group(self, *args, **kwargs):
        return self._register("group", *args, **kwargs)

    def _register(self, _type, *args, **kwargs):
        aliases = kwargs.pop("aliases", [])
        decorator = getattr(super(), _type)(*args, **kwargs)
        if not aliases:
            return decorator

        def _decorator(f):
            cmd = decorator(f)
            self._cmd2aliases[cmd.name] = aliases
            for alias in aliases:
                self._alias2cmd[alias] = cmd.name
            return cmd

        return _decorator

    def resolve_alias(self, cmd_name):
        if cmd_name in self._alias2cmd:
            return self._alias2cmd[cmd_name]
        return cmd_name

    def get_command(self, ctx, cmd_name):
        # see if the command matches an alias
        # and resolve an actual command name
        cmd_name = self.resolve_alias(cmd_name)

        # see if we can find a command by that specific name
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command

        # if that fails, let's look for any partial matches
        # allows user to shorten commands to shortest unique string
        matches = list(
            {
                self.resolve_alias(cmd)
                for cmd in self.list_commands(ctx) + list(self._alias2cmd.keys())
                if cmd.startswith(cmd_name)
            },
        )

        # no matches no command
        if not matches:
            return None

        # one match then we can resolve the match
        # and try getting the command again
        if len(matches) == 1:
            return super().get_command(ctx, matches[0])

        # otherwise the string matched but was not unique
        # to a single command and we have to bail out
        ctx.fail(
            f"Unknown command '{cmd_name}. Did you mean any of these: "
            f"{', '.join(sorted(matches))}?",
        )

        return None

    def format_commands(self, ctx, formatter):
        rows = []
        cmds = []

        for sub in self.list_commands(ctx):
            cmd = self.get_command(ctx, sub)
            if cmd is None or cmd.hidden:
                continue
            cmds.append((sub, cmd))

        if not cmds:
            return

        max_len = max(len(cmd[0]) for cmd in cmds)
        limit = formatter.width - 6 - max_len

        for sub, cmd in cmds:
            try:
                aliases = ",".join(sorted(self._cmd2aliases[sub]))
            except KeyError:
                pass
            else:
                sub = f"{sub} ({aliases})"

            cmd_help = cmd.get_short_help_str(limit)
            rows.append((sub, cmd_help))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)

    def resolve_command(self, ctx, args):
        # always return the full command name
        _, cmd, args = super().resolve_command(ctx, args)
        return cmd.name if cmd else None, cmd, args


class VariableFile(click.File):
    name = "variable file"

    def convert(self, value, param, ctx):
        import shlex

        f = super().convert(value, param, ctx)

        env = {}
        for line in f.readlines():
            name, val = line.split("=")
            val = shlex.split(val)

            if len(val) != 1:
                self.fail(f"Malformed variable file: {value}", param, ctx)

            env[name] = val[0]

        f.close()

        return env


class Variable(click.ParamType):
    name = "key/val pair"

    def convert(self, value, param, ctx):
        return {value[0]: value[1]}


def merge_vars1(ctx, param, value):
    env = {}
    for _vars in value:
        env.update(_vars)
    return env


def merge_vars2(ctx, param, value):
    env = ctx.params.pop("additional_variable_files", {})
    for key, val in value:
        env[key] = val
    return env


def additional_variables(func):
    func = click.argument(
        "additional_variable_files",
        nargs=-1,
        type=VariableFile(),
        callback=merge_vars1,
        is_eager=True,
    )(func)
    return click.option(
        "-x",
        "--var",
        "additional_variables",
        nargs=2,
        multiple=True,
        callback=merge_vars2,
        default={},
        help="Additional templating variables",
    )(func)


def silence_templating_errors(func):
    return click.option(
        "--silence-templating-errors",
        is_flag=True,
    )(func)
