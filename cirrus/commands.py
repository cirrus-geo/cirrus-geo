import os
import logging

from pathlib import Path

from cirrus.project import Project


logger = logging.getLogger(__name__)


class Singleton(object):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


class Command(Singleton):
    help=""

    def get(self, keyname, value=None):
        return getattr(self, keyname, value)

    def collect_args(self, subparser):
        pass

    def postprocess_args(self, parser, args):
        pass

    def __call__(self, args):
        raise NotImplementedError('Subclasses of {} must implement a __call__ method'.format(self.__class__))


class Init(Command):
    help="Initialize a cirrus project in the current directory"

    def collect_args(self, subparser):
        subparser.add_argument(
            'directory',
            nargs='?',
            default=os.getcwd(),
            type=Path,
            help='directory in which to initialize cirrus project',
        )

    def postprocess_args(self, parser, args):
        args.directory = args.directory.resolve()

    def __call__(self, args):
        try:
            Project.new(args.directory)
        except FileNotFoundError:
            logger.error("Unable to initialize project: '%s' not found", args.directory)
        else:
            logger.info("Succesfully initialized project in '%s'", args.directory)

