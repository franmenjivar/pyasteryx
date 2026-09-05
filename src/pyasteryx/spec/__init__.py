"""Specification layer: data-driven, edition-aware ASTERIX category definitions.

Categories are described by JSON files under ``spec/data/cat<NNN>/<edition>.json``
and loaded into the frozen dataclasses in :mod:`pyasteryx.spec.model`. A
:class:`SpecRegistry` holds those specs grouped by category and edition, since the
same category number decodes differently across editions of the standard.

Loading is lazy. :meth:`SpecRegistry.with_bundled` indexes the bundled files by
path — which already encodes the category and edition — and parses a file only
when that category and edition is first decoded. A decoder pointed at a CAT062
feed therefore never pays for the CAT021 or CAT048 specifications it will not
touch.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pyasteryx.exceptions import SpecificationError, UnsupportedCategoryError
from pyasteryx.spec.loader import (
    category_from_dict,
    iter_bundled_paths,
    load_bundled_categories,
    load_category_file,
)
from pyasteryx.spec.model import CategorySpec, ExtentSpec, FieldSpec, ItemSpec

__all__ = [
    "CategorySpec",
    "ExtentSpec",
    "FieldSpec",
    "ItemSpec",
    "SpecRegistry",
    "category_from_dict",
    "iter_bundled_paths",
    "load_bundled_categories",
    "load_category_file",
]


def _version_key(edition: str) -> tuple[int, ...]:
    """Sort key for an edition string such as ``"2.6"`` or ``"1.21"``."""
    parts = []
    for chunk in edition.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


class SpecRegistry:
    """Loaded category specifications, grouped by category and edition.

    When a category is decoded without an explicit edition, the newest known
    edition is used.

    A registry may hold specifications in two states: already parsed, and known
    but not yet parsed (a file path). :meth:`get` transparently promotes the
    second to the first and caches the result, so the distinction is invisible
    except in how much work construction does.

    Args:
        specs: Specifications to register eagerly.
    """

    __slots__ = ("_by_cat", "_paths")

    def __init__(self, specs: Iterable[CategorySpec] | None = None) -> None:
        # category -> {edition -> CategorySpec}, for what has been parsed.
        self._by_cat: dict[int, dict[str, CategorySpec]] = {}
        # category -> {edition -> Path}, for what is known but not yet parsed.
        self._paths: dict[int, dict[str, Path]] = {}
        for spec in specs or ():
            self.register(spec)

    @classmethod
    def with_bundled(cls) -> SpecRegistry:
        """Create a registry over every bundled category and edition, lazily.

        Only the data directory is scanned; no specification is parsed until it
        is first used. Use :func:`~pyasteryx.spec.loader.load_bundled_categories`
        with the constructor if you want everything parsed up front, for example
        to validate every bundled file.
        """
        registry = cls()
        for category, edition, path in iter_bundled_paths():
            registry._paths.setdefault(category, {})[edition] = path
        return registry

    def register(self, spec: CategorySpec) -> None:
        """Add or replace a specification for a given category/edition.

        A registered specification takes precedence over a bundled file for the
        same category and edition, which is how you override a bundled spec.
        """
        self._by_cat.setdefault(spec.category, {})[spec.edition] = spec

    def get(self, category: int, edition: str | None = None) -> CategorySpec:
        """Return the spec for ``category`` (and optional ``edition``).

        With no edition, the newest known edition is returned. A specification
        that has not been parsed yet is parsed here and cached, so the cost is
        paid once, on first use.

        Raises:
            UnsupportedCategoryError: If the category has no known editions.
            SpecificationError: If a specific edition is requested but unknown,
                or if the specification file is malformed.
        """
        loaded = self._by_cat.get(category)
        if edition is None:
            edition = self.latest_edition(category)

        if loaded is not None and edition in loaded:
            return loaded[edition]

        path = self._paths.get(category, {}).get(edition)
        if path is not None:
            spec = load_category_file(path)
            self._by_cat.setdefault(category, {})[edition] = spec
            return spec

        available = ", ".join(self.editions(category)) or "none"
        raise SpecificationError(
            f"CAT{category:03d}: edition {edition!r} not loaded (available: {available})"
        )

    def latest_edition(self, category: int) -> str:
        """Return the newest known edition string for a category."""
        editions = self.editions(category)
        if not editions:
            raise UnsupportedCategoryError(category)
        return editions[-1]

    def editions(self, category: int) -> list[str]:
        """Return the known editions for a category, newest last.

        Includes editions that have not been parsed yet.
        """
        known = set(self._by_cat.get(category, ())) | set(self._paths.get(category, ()))
        return sorted(known, key=_version_key)

    def categories(self) -> Iterable[int]:
        """Return the category numbers known to this registry, parsed or not."""
        return self._by_cat.keys() | self._paths.keys()

    def is_loaded(self, category: int, edition: str | None = None) -> bool:
        """Whether a specification has actually been parsed yet.

        Mostly useful for tests and diagnostics; :meth:`get` does the right thing
        regardless.
        """
        if edition is None:
            edition = self.latest_edition(category)
        return edition in self._by_cat.get(category, {})

    def __contains__(self, category: int) -> bool:
        return category in self._by_cat or category in self._paths
