"""Tests for the package's public surface and metadata."""

from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

import pyasteryx


def test_version_matches_the_project_metadata():
    """A version bumped in one place and not the other is a broken release.

    Read with a regex rather than tomllib, which is 3.11+ while the package
    supports 3.10.
    """
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE)
    assert match, "no version found in pyproject.toml"
    assert pyasteryx.__version__ == match.group(1)


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
