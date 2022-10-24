import copy
import logging
import sys
from pathlib import Path
from typing import Callable, Type, TypeVar

from cirrus.core.exceptions import ComponentError
from cirrus.core.utils import misc
from cirrus.core.utils.console import console

logger = logging.getLogger(__name__)


T = TypeVar("T", bound="ComponentFile")
Component = TypeVar("Component", bound="Component")


class ComponentFile:
    def __init__(
        self,
        name: str,
        optional: bool = False,
        path: Path = None,
        content_fn: Callable[[Type[Component]], str] = None,
    ) -> None:
        self.name = name
        self.required = not optional
        self._content = None
        self.parent = None

        if not path:
            path = Path(self.name)

        self.base_path = path

        if content_fn or not hasattr(self, "content_fn"):
            self.content_fn = content_fn

        # store a reference to the console to
        # make show overrides easier for users
        self.console = console

        if self.required and not self.content_fn:
            raise ValueError("Required files must have a content_fn defined.")

    @property
    def content(self):
        if self._content is None:
            try:
                self._content = self.path.read_text()
            except FileNotFoundError as e:
                if self.required:
                    raise ComponentError(
                        f"{self.__class__.__name__} at '{self.relative_path()}': unable to open for read"
                    ) from e
                else:
                    logging.debug(
                        f"{self.__class__.__name__} at '{self.relative_path()}': unable to open for read, defaulting to empty",
                    )
                    self._content = ""
        return self._content

    def relative_path(self):
        return misc.relative_to_cwd(self.path)

    def exists(self):
        return self.path.is_file()

    def validate(self, required=None):
        if required is None:
            required = self.required

        if required and not self.exists():
            raise ComponentError(
                f"Cannot load {self.__class__.__name__} from '{self.relative_path()}': not a file"
            )

    @property
    def path(self) -> Path:
        if self.parent:
            return self.parent.path.joinpath(self.base_path)
        return self.base_path

    @path.setter
    def path(self, path: Path) -> None:
        if path.is_absolute():
            raise ValueError(f"Path cannot be absolute: {path}")
        self.base_path = path

    def _copy_to_component(self, parent_component: Type[Component]) -> T:
        self = copy.copy(self)
        self.parent = parent_component
        return self

    def copy_to_component(self, component: Type[Component], name: str) -> None:
        self = self._copy_to_component(component)
        setattr(component, name, self)
        component.files[name] = self

    def init(self, parent_component: Type[Component]) -> None:
        if self.content_fn is None:
            return
        path = parent_component.path.joinpath(self.path)
        path.write_text(self.content_fn(parent_component))

    def show(self):
        if sys.stdout.isatty():
            self.console.print_escaped(self.content)
        else:
            print(self.content)
