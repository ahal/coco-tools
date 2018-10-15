import os

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

PACKAGE_VERSION = '0.1.0'
DESC = "Collection of per-test coverage analysis types for exploring data."
with open(os.path.join(here, 'README.md')) as fh:
    README = fh.read()

# 'tkinter' is also required and
# must  be installed manually.
DEPS = [
    'requests >= 2.18.3',
    'numpy',
    'matplotlib',
    'ruamel.yaml',
]

setup(
    name='pertestcoverage-analysis',
    version=PACKAGE_VERSION,
    description=DESC,
    long_description=README,
    keywords='mozilla',
    author='Gregory Mierzwinski',
    author_email='gmierz2@outlook.com',
    url='https://github.com/gmierz/coco-tools',
    license='MPL',
    packages=[
        'pertestcoverage',
        'pertestcoverage.analysistypes',
        'pertestcoverage.utils',
        'pertestcoverage.utils.cocoanalyze'
    ],
    include_package_data=True,
    install_requires=DEPS,
    entry_points="""
    # -*- Entry points: -*-
    [console_scripts]
    ptc = pertestcoverage.cli:cli
    """,
)