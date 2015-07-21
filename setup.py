#!/usr/bin/env python

import os, sys
import piera

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

packages = [
    'piera',
]

requires = [
    'pyyaml'
]

with open('README.md') as f:
    readme = f.read()

setup(
    name='piera',
    version=piera.__VERSION__,
    description='a python hiera parser',
    long_description=readme + '\n\n',
    author='Andrei Zbikowski',
    author_email='andrei.zbikowski@gmail.com',
    url='http://github.com/b1naryth1ef/piera',
    packages=packages,
    package_data={"": ["README.md"]},
    package_dir={'piera': 'piera'},
    include_package_data=True,
    install_requires=requires,
    license='Apache 2.0',
    zip_safe=False,
    classifiers=(
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
    ),
)
