"""Tests for the package's public surface and metadata."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

import pyasteryx


def test_version_matches_the_project_metadata():
    """A version bumped in one place and not the other is a broken release."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert pyasteryx.__version__ == declared


def test_installed_distribution_is_named_pyasteryx():
    assert metadata.version("pyasteryx") == pyasteryx.__version__


def test_public_api_is_exported():
    for name in pyasteryx.__all__:
        assert hasattr(pyasteryx, name), f"{name} is in __all__ but not importable"


def test_headline_names_are_public():
    for name in ("Decoder", "Message", "Track", "tracks", "SpecRegistry", "AsteryxError"):
        assert name in pyasteryx.__all__


def test_importing_the_package_pulls_in_no_third_party_dependency():
    """``import pyasteryx`` must stay dependency-free; extras are imported lazily."""
    import subprocess
    import sys

    code = (
        "import sys, pyasteryx;"
        "heavy = {'pandas', 'pyarrow', 'polars', 'pyspark'} & set(sys.modules);"
        "print(sorted(heavy))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "[]", out.stdout
