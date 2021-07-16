import argparse
import sys

from cirrus import commands


class CLI(object):
    def __init__(self, prog, description):
        self.parser = argparse.ArgumentParser(
            prog=prog,
            description=description,
        )
        self._subparsers = self.parser.add_subparsers(
            title='subcommands',
            dest='subcommand',
        )
        self._subparsers.metavar = '{command}'
        self._show_list = []

    def add_cmd(self, cmd):
        name = cmd.get('name', cmd.__class__.__name__.lower())
        parser = self._subparsers.add_parser(name, help=cmd.get('help', None), aliases=cmd.get('aliases', []))
        cmd.collect_args(parser)
        parser.set_defaults(_cmd=cmd)

    def __call__(self, argv=None, ns=None):
        # TODO: fix command hiding, this doesn't really work
        # overriding subparser metavar to prevent display of 'hidden' commands
        #self._subparsers.metavar = '{%s}'%','.join(self._show_list)
        args = self.parser.parse_args(argv, ns)

        if args.subcommand is None:
            print('error: subcommand required')
            self.parser.print_help()
            sys.exit(2)

        args._cmd.postprocess_args(self.parser, args)
        return args._cmd(args)


def main(argv=None):
    cli = CLI(
        prog='ggw',
        description='GRACE GroundWater (ggw) exploration tool',
    )
    cli.add_cmd(commands.Build())

    return cli(argv)


if __name__ == '__main__':
    main()
