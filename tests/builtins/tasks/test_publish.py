import pytest

from cirrus.test import run_task


def test_empty_event():
    with pytest.raises(Exception):
        run_task("publish", {})
