"""Package setup."""

from pathlib import Path
import re
from setuptools import setup, find_packages

root_dir = Path(__file__).parent.resolve()

exec(open(root_dir / "trs_filer" / "version.py").read())

file_name = root_dir / "README.md"
with open(file_name, "r") as _file:
    long_description = _file.read()

install_requires = []
req = root_dir / 'requirements.txt'
with open(req, "r") as _file:
    # without comments (as for pip) and blank lines
    install_requires = [
        requirement for requirement in (
            re.sub(r"(^|\s)#.*$", "", line).strip() for line in _file
        ) if requirement
    ]

setup(
    name="trs-filer",
    version=__version__,  # noqa: F821
    author="ELIXIR Cloud & AAI",
    author_email="nagorikushagra9@gmail.com",
    maintainer="Kushagra Nagori",
    maintainer_email="nagorikushagra9@gmail.com",
    description="Lightweight, flexible Flask/Gunicorn-based \
                    GA4GH TRS implementation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="Apache License 2.0",
    url="https://github.com/elixir-cloud-aai/trs-filer.git",
    packages=find_packages(),
    keywords=(
        'ga4gh trs elixir rest restful api app server openapi '
        'swagger mongodb python flask'
    ),
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.13",
    ],
    # The Python version of the base image in the `Dockerfile`, the only one
    # the app is tested with
    python_requires=">=3.13",
    project_urls={
        "Repository": "https://github.com/elixir-cloud-aai/trs-filer",
        "ELIXIR Cloud & AAI": "https://elixir-europe.github.io/cloud/",
        "Tracker": "https://github.com/elixir-cloud-aai/trs-filer/issues",
    },
    install_requires=install_requires,
)
