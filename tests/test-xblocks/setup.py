"""Set up for XBlocks for test"""
from setuptools import setup

setup(
    name='XBlocks for test',
    version='0.1',
    description='Library of XBlocks for use in tests',
    packages=['test_xblocks'],
    install_requires=[
        'XBlock',
    ],
    entry_points={
        'xblock.v1': [
            'test_fields = test_xblocks.test_xblocks:TestFieldsBlock',
        ]
    }
)
