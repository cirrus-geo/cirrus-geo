from cirrus.test import run_function


def test_empty_event():
    run_function("update-state", {})
