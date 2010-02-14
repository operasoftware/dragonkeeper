#!/usr/bin/env python

from dragonkeeper.common import __version__ as VERSION 

try:
    from setuptools import setup, find_packages
    addl_args = dict(
            packages = find_packages(),
            entry_points = {        
            'console_scripts': [
                'dragonkeeper = dragonkeeper.dragonkeeper:main_func'
                ],
            },
        )
        
except ImportError:
    from distutils.core import setup
    addl_args = dict(
        packages = [
            'dragonkeeper',
            ],
        )
        
setup(
    name='dragonkeeper',
    version=VERSION,
    url='http://bitbucket.org/scope/dragonkeeper/',
    author='Christian Krebs, Rune Halvorsen, Jan Borsodi',
    author_email='chrisk@opera.com, runeh@opera.com, jborsodi@opera.com',
    data_files=[('dragonkeeper', ['dragonkeeper/favicon.ico'])],
    description='An HTTP proxy for Opera Dragonfly development',
    long_description=open("README").read(),
    **addl_args
    )