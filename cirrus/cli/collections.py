import logging

from itertools import chain

from cirrus.cli.components import (
    CoreTask,
    Feeder,
    Task,
    Workflow,
)
from cirrus.cli.resources import Resource


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

        if not self.element_class.user_extendable:
            self.user_dir_name = None
        else:
            self.user_dir_name = user_dir_name if user_dir_name is not None else self.name

        self._elements = None
        self.project = None
        self.parent = None

    @property
    def elements(self):
        if self._elements is None:
            self.find()
        return self._elements

    @property
    def user_dir(self):
        if self.user_dir_name is None:
            return None
        if self.project is None or self.project.path is None:
            logger.warning(
                f'No cirrus project specified; limited to built-in {self.display_name}.',
            )
            return None
        return self.project.path.joinpath(self.user_dir_name)

    def get_search_dirs(self):
        user_dir = self.user_dir
        if user_dir:
            return [self.user_dir]
        else:
            return None

    def find(self):
        self._elements = {}
        for element in self.element_class.find(search_dirs=self.get_search_dirs()):
            if element.name in self._elements:
                logger.warning(
                    "Duplicate %s declaration '%s', overriding",
                    self.element_class.name,
                    element.name,
                )
            self._elements[element.name] = element

    def create(self, name: str):
        return self.element_class.create(name, self.user_dir)

    def reset_elements(self):
        self._elements = None

    def register_project(self, project):
        self.project = project
        self.reset_elements()

    def add_create_command(self, create_cmd):
        if self.enable_cli and hasattr(self.element_class, 'add_create_command'):
            self.element_class.add_create_command(self, create_cmd)

    def add_show_command(self, show_cmd):
        if self.enable_cli and hasattr(self.element_class, 'add_show_command'):
            self.element_class.add_show_command(self, show_cmd)


    def __iter__(self):
        return self.elements.__iter__()

    def __getitem__(self, name):
        return self.elements[name]

    def items(self):
        return self.elements.items()

    def keys(self):
        return self.elements.values()

    def values(self):
        return self.elements.values()


class ResourceCollection(Collection):
    def find(self):
        self._elements = {}

        def resource_finder():
            yield from self.element_class.find(search_dirs=self.get_search_dirs())
            yield from chain.from_iterable(filter(bool, map(
                lambda r: r.batch_resources if r.batch_enabled else None,
                self.parent.tasks.values(),
            )))

        for resource in resource_finder():
            if resource.name in self._elements:
                logger.warning(
                    "Duplicate %s declaration '%s', overriding",
                    self.element_class.name,
                    resource.name,
                )
            self._elements[resource.name] = resource


class Collections():
    def __init__(self, collections, project=None):
        self.collections = collections
        self.project = project

        for collection in self.collections:
            self.register_collection(collection)

    @property
    def lambda_collections(self):
        from cirrus.cli.components.base import Lambda
        return [c for c in self.collections if issubclass(c.element_class, Lambda)]

    @property
    def stepfunction_collections(self):
        from cirrus.cli.components.base import StepFunction
        return [c for c in self.collections if issubclass(c.element_class, StepFunction)]

    @property
    def resource_collections(self):
        from cirrus.cli.resources import Resource
        return [c for c in self.collections if issubclass(c.element_class, Resource)]

    @property
    def extendable_collections(self):
        return [c for c in self.collections if c.element_class.user_extendable]

    def register_collection(self, collection):
        setattr(self, collection.name, collection)
        collection.parent = self
        collection.register_project(self.project)

    def register_project(self, project):
        self.project = project
        for collection in self.collections:
            collection.register_project(self.project)


collections = Collections([
    Collection(
        'core-tasks',
        CoreTask,
        display_name='Core Tasks',
    ),
    Collection(
        'feeders',
        Feeder,
    ),
    ResourceCollection(
        'resources',
        Resource,
    ),
    Collection(
        'tasks',
        Task,
    ),
    Collection(
        'workflows',
        Workflow,
    ),
])
