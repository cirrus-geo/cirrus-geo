# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# inherit defaults from base cirrus config
import os

from pathlib import Path

from cirrus.docs.base_conf import *


THIS_DIR = Path(__file__).resolve().parent


# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))


# -- Project information -----------------------------------------------------

project = 'cirrus-geo'
version = os.environ.get('CIRRUS_VERSION', None)


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions += [
    'sphinx_rtd_theme',
]

# Add any paths that contain templates here, relative to this directory.
templates_path += [
    str(THIS_DIR.joinpath('_templates')),
]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns += []

# allow substituting the project name in documents
rst_epilog = f'.. |project_name| replace:: {project}'


# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path += [
    str(THIS_DIR.joinpath('_static')),
]

# A list of paths that contain extra files not directly related to the
# documentation, such as robots.txt or .htaccess. Relative paths are taken as
# relative to the configuration directory. They are copied to the output
# directory. They will overwrite any existing file of the same name.
html_extra_path += [
    str(THIS_DIR.joinpath('_extra')),
]

html_js_files = [
    'js/versions-loader.js',
]
