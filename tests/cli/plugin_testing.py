import sys
import importlib

from pathlib import Path

try:
    from importlib import metadata
except ImportError:
    import importlib_metadata as metadata


class TestPluginFinder(metadata.DistributionFinder):
    def __init__(self, plugin_dist_path, *args, **kwargs):
        self.plugin_dist_path = plugin_dist_path
        self.file_finder = importlib.machinery.FileFinder(
            str(self.plugin_dist_path.parent)
        )
        super().__init__(*args, **kwargs)

    def find_spec(self, fullname, *args, **kwargs):
        return self.file_finder.find_spec(fullname)

    def find_distributions(self, context=None):
        yield metadata.Distribution.at(self.plugin_dist_path)

    def __eq__(self, other):
        return (
            hasattr(other, 'plugin_dist_path')
            and self.plugin_dist_path == other.plugin_dist_path
        )


def add_plugin_finder(plugin_dist_path):
    tpf = TestPluginFinder(plugin_dist_path)
    if not tpf in sys.meta_path:
        sys.meta_path.append(tpf)


def remove_plugin_finder(plugin_dist_path):
    try:
        sys.meta_path.remove(TestPluginFinder(plugin_dist_path))
    except ValueError:
        pass
