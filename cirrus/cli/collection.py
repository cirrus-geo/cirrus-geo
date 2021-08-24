import logging

from cirrus.cli.project import project


logger = logging.getLogger(__name__)


class Collection():
    def __init__(
        self,
        name,
        element_class,
        enable_cli=True,
        display_name=None,
        user_dir_name=None,
    ):
        self.name = name
        self.element_class = element_class
        self.enable_cli = enable_cli
        self.display_name = display_name if display_name is not None else self.name.capitalize()
        self.user_dir_name = user_dir_name if user_dir_name is not None else self.name

        self._elements = None

        self.register_to_project()

        if self.enable_cli:
            if hasattr(self.element_class, 'add_create_command'):
                self.element_class.add_create_command()
            if hasattr(self.element_class, 'add_show_command'):
                self.element_class.add_show_command(self)

    @property
    def elements(self):
        if self._elements is None:
            self._elements = {}
            for element in self.element_class.find():
                if element.name in self._elements:
                    logger.warning(
                        "Duplicate %s declaration '%s', overriding",
                        self.element_class.name,
                        element.name,
                    )
                self._elements[element.name] = element
        return self._elements

    def register_to_project(self):
        project.collections.append(self)
        setattr(project, self.name, self)

    def __iter__(self):
        return self.elements.__iter__()

    def __getitem__(self, name):
        return self.elements[name]

    def items(self):
        return self.elements.items()

    def values(self):
        return self.elements.values()
