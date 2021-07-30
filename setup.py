#!/usr/bin/env python
import os
import os.path

from setuptools import setup, find_packages

from cirrus.cli.commands import DESC
from cirrus.cli.constants import SUPPORTED_BACKENDS


HERE = os.path.abspath(os.path.dirname(__file__))
VERSION = os.environ.get('CIRRUS_VERSION', '0.0.0')


with open(os.path.join(HERE, 'README.md'), encoding='utf-8') as f:
    readme = f.read()

with open(os.path.join(HERE, 'requirements.txt'), encoding='utf-8') as f:
    all_reqs = f.read().split('\n')

install_requires = [x.strip() for x in all_reqs if 'git+' not in x]
dependency_links = [x.strip().replace('git+', '') for x in all_reqs if 'git+' not in x]


package_data = {
    'cirrus': [
        'cli/feeders/config/**/*',
        'cli/tasks/config/**/*',
        'cli/workflows/config/**/*',
        'cli/config/*',
    ],
}


setup(
    name='cirrus',
    packages=find_packages(exclude=['docs', 'test*']),
    version=VERSION,
    description=DESC,
    long_description=readme,
    author='Matthew Hanson (matthewhanson), Jarrett Keifer (jkeifer), Element 84',
    url='https://github.com/cirrus-geo/cirrus',
    install_requires=install_requires,
    dependency_links=dependency_links,
        classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
        'Programming Language :: Python :: 3.9'
    ],
    license='Apache-2.0',
    include_package_data=True,
    package_data=package_data,
    entry_points='''
        [console_scripts]
        cirrus=cirrus.cli.commands:cli
    ''',
)