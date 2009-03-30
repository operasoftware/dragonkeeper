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
    name = 'dragonkeeper',
    version = VERSION,
    author = 'Christian Krebs, Rune Halvorsen, Jan Borsodi',
    author_email = 'chrisk@opera.com, runeh@opera.com, jborsodi@opera.com',
    data_files = [('dragonkeeperResources', ['dragonkeeper/favicon.ico'])],
    description = 'A HTTP interace for developping Opera Dragonfly',
    **addl_args
    )