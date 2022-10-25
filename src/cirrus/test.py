from copy import deepcopy

from cirrus.core.components import Feeder, Function, Task


def get_lambda_handler(component_class, name):
    try:
        component = component_class[name]
    except KeyError:
        raise Exception(f"Unknown {component.type} '{name}'")

    return component.import_handler()


def run_feeder(name, event):
    return get_lambda_handler(Feeder, name)(deepcopy(event), {})


def run_function(name, event):
    return get_lambda_handler(Function, name)(deepcopy(event), {})


def run_task(name, event):
    return get_lambda_handler(Task, name)(deepcopy(event), {})
