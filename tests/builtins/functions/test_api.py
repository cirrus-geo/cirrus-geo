import pytest

from cirrus.test import run_function


def test_empty_event():
    with pytest.raises(Exception):
        run_function("api", {})
