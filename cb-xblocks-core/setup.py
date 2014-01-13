"""Set up for Course Builder XBlocks"""
from setuptools import setup

setup(
    name='Course Builder Core XBlocks',
    version='0.1',
    description='Core XBlock Library for Course Builder',
    packages=['cb_xblocks_core'],
    install_requires=[
        'XBlock',
    ],
    entry_points={
        'xblock.v1': [
            'sequential = cb_xblocks_core.cb_xblocks_core:SequenceBlock',
            'video = cb_xblocks_core.cb_xblocks_core:VideoBlock',
            'cbquestion = cb_xblocks_core.cb_xblocks_core:QuestionBlock',
            'html = cb_xblocks_core.cb_xblocks_core:HtmlBlock',
            'vertical = cb_xblocks_core.cb_xblocks_core:VerticalBlock',
            'problem = cb_xblocks_core.problem:ProblemBlock'
        ]
    }
)
