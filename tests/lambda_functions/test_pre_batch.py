import pytest

from cirrus.lambda_functions.pre_batch import lambda_handler as pre_batch


def test_empty_event():
    with pytest.raises(Exception):
        pre_batch({}, {})
