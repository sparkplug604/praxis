"""Compatibility shim for older pip editable installs.

Modern builds use `pyproject.toml`; this file exists so older pip versions can
still run `python3 -m pip install -e .` from a checkout.
"""

from setuptools import find_packages, setup


setup(
    name="praxis-ktos",
    version="0.1.0",
    description="Agent-agnostic knowledge-to-skill framework.",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    include_package_data=True,
    package_data={"praxis": ["demo_data/stackoverflow_developer_survey/*"]},
    entry_points={"console_scripts": ["praxis=praxis.cli:main"]},
)
