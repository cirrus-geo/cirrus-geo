import pytest

from cirrus.core.utils import plugins


def test_iter_plugins_and_resources():
    plugin_list = list(plugins.iter_plugins())
    assert len(plugin_list) == 0, "shouldn't be any plugins installed"
    resource_list = list(plugins.iter_resources())
    assert len(resource_list) == 1, "should only be one resource EntryPoint"


def test_iter_entry_points_raises(mocker):
    entry_point_mock = mocker.patch("cirrus.core.utils.plugins.entry_points")
    entry_point_mock.return_value = None
    with pytest.raises(RuntimeError):
        list(plugins.iter_entry_points("banana"))
