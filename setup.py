#!/usr/bin/env python
import os
import os.path

from setuptools import setup, find_namespace_packages

from src.cirrus.cli.constants import DESC


HERE = os.path.abspath(os.path.dirname(__file__))
VERSION = os.environ.get('CIRRUS_VERSION', '0.0.0')


with open(os.path.join(HERE, 'README.md'), encoding='utf-8') as f:
    readme = f.read()

with open(os.path.join(HERE, 'requirements.txt'), encoding='utf-8') as f:
    reqs = f.read().split('\n')

install_requires = [x.strip() for x in reqs if 'git+' not in x]
dependency_links = [x.strip().replace('git+', '') for x in reqs if 'git+' not in x]


package_data = {
    'cirrus': [
        'builtins/**/**/*',
        'builtins/**/*',
        'core/config/*',
    ],
}


setup(
    name='cirrus-geo',
    packages=find_namespace_packages('src'),
    package_dir={'': 'src'},
    version=VERSION,
    description=DESC,
    long_description=readme,
    long_description_content_type='text/markdown',
    author='Matthew Hanson (matthewhanson), Jarrett Keifer (jkeifer), Element 84',
    url='https://github.com/cirrus-geo/cirrus',
    install_requires=install_requires,
    dependency_links=dependency_links,
        classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9'
    ],
    license='Apache-2.0',
    include_package_data=True,
    package_data=package_data,
    entry_points='''
        [console_scripts]
        cirrus=cirrus.cli.__main__:main
    ''',
)
