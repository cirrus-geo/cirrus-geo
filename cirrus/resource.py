from abc import ABC
from pathlib import Path


class ResourceFileBase(ABC):
    filename = None

    def __init__(self, parent_resource):
        if not self.filename:
            raise NotImplementedError(
                f"Class {self.__class__.__name__} must define 'filename' attribute"
            )

        self.path = parent_resource.path.joinpath(self.filename)
        if not self.path.is_file():
            raise FileNotFoundError(
                f"Cannot load {self.__class__.__name__} from '{self.path}': not a file"
            )


class Readme(ResourceFileBase):
    filename = 'README.md'


class Requirements(ResourceFileBase):
    filename = 'requirements.txt'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with self.path.open() as f:
            self.content = f.read()


class Definition(ResourceFileBase):
    filename = 'definition.yml'


class ResourceBase(ABC):
    required_files = [Definition]
    optional_files = []

    def __init__(self, path: Path):
        self.path = path

        if not self.path.is_dir():
            raise FileNotFoundError(
                f"Cannot load {self.__class__.__name__} from '{self.path}': not a directory"
            )

        self.name = path.name

        self.files = []
        for filetype in self.required_files:
            self.files.append(filetype(self))

        for filetype in self.optional_files:
            try:
                self.files.append(filetype(self))
            except FileNotFoundError:
                pass


def get_resources_from_dir(d: Path, c: ResourceBase):
    for resource_dir in d.iterdir():
        try:
            yield c(resource_dir)
        except FileNotFoundError:
            continue
