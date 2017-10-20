#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

long_description = 'See https://github.com/Koenkk/autosub-sync'
setup(
    name='autosubsync',
    version='0.1',
    description='Automagically synchronize subtitles.',
    long_description=long_description,
    author='Koen Kanters',
    author_email='koenkanters94@gmail.com',
    url='https://github.com/Koenkk/autosub-sync',
    packages=['autosubsync'],
    license=open("LICENSE").read()
)
