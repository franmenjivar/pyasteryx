"""Tests that bundled specifications are discovered cheaply and parsed on demand.

A decoder pointed at a CAT062 feed must not pay to parse CAT021 and CAT048. The
registry therefore indexes the bundled files by path — the path already encodes
the category and edition — and parses one only when it is first decoded.
"""

from __future__ import annotations

import json

import pytest

from pyasteryx import Decoder, SpecRegistry
from pyasteryx.exceptions import SpecificationError, UnsupportedCategoryError
from pyasteryx.spec import category_from_dict, iter_bundled_paths, load_bundled_categories


class TestDiscovery:
    def test_finds_every_bundled_file_without_parsing(self):
        found = list(iter_bundled_paths())
        assert {(c, e) for c, e, _ in found} == {
            (21, "2.4"), (21, "2.6"), (48, "1.21"), (62, "1.17"), (62, "1.18"),
        }

    def test_reports_categories_and_editions_before_anything_is_parsed(self):
        registry = SpecRegistry.with_bundled()
        assert sorted(registry.categories()) == [21, 48, 62]
        assert registry.editions(62) == ["1.17", "1.18"]
        assert registry.latest_edition(62) == "1.18"
        assert 62 in registry
        assert not any(registry.is_loaded(c) for c in (21, 48, 62))


class TestLaziness:
    def test_nothing_is_parsed_on_construction(self):
        assert not SpecRegistry.with_bundled().is_loaded(62)

    def test_get_parses_only_the_category_asked_for(self):
        registry = SpecRegistry.with_bundled()
        registry.get(62)
        assert registry.is_loaded(62)
        assert not registry.is_loaded(21)
        assert not registry.is_loaded(48)

    def test_get_parses_only_the_edition_asked_for(self):
        registry = SpecRegistry.with_bundled()
        registry.get(62, "1.17")
        assert registry.is_loaded(62, "1.17")
        assert not registry.is_loaded(62, "1.18")

    def test_a_parsed_spec_is_cached_not_reparsed(self):
        registry = SpecRegistry.with_bundled()
        assert registry.get(62) is registry.get(62)

    def test_decoding_cat062_leaves_the_other_categories_unparsed(self, cat062_block):
        decoder = Decoder()
        decoder.decode(cat062_block)
        assert decoder.registry.is_loaded(62)
        assert not decoder.registry.is_loaded(21)


class TestBehaviourIsUnchanged:
    """Laziness must be invisible: same specs, same errors, same precedence."""

    def test_lazy_and_eager_registries_agree(self):
        lazy = SpecRegistry.with_bundled()
        eager = SpecRegistry(load_bundled_categories())
        assert sorted(lazy.categories()) == sorted(eager.categories())
        for category in eager.categories():
            assert lazy.editions(category) == eager.editions(category)
            assert lazy.get(category).items.keys() == eager.get(category).items.keys()
            assert lazy.get(category).uap == eager.get(category).uap

    def test_unknown_category_still_raises(self):
        with pytest.raises(UnsupportedCategoryError):
            SpecRegistry.with_bundled().get(999)

    def test_unknown_edition_still_raises_and_lists_what_exists(self):
        with pytest.raises(SpecificationError, match=r"1\.17, 1\.18"):
            SpecRegistry.with_bundled().get(62, "9.99")

    def test_a_registered_spec_overrides_a_bundled_file(self, cat062_block):
        """register() must win over the lazily discovered file for the same edition."""
        registry = SpecRegistry.with_bundled()
        raw = {
            "category": 62,
            "edition": "1.18",
            "name": "custom",
            "uap": ["I062/010"],
            "items": [
                {
                    "id": "I062/010",
                    "format": "fixed",
                    "length": 2,
                    "fields": [{"name": "MINE", "from": 16, "to": 1}],
                }
            ],
        }
        registry.register(category_from_dict(raw))
        assert registry.get(62).name == "custom"
        assert "MINE" in registry.get(62).items["I062/010"].fields[0].name

    def test_a_malformed_file_raises_when_it_is_finally_parsed(self, tmp_path, monkeypatch):
        """A broken spec must surface as SpecificationError, not at import time."""
        bad = tmp_path / "cat099" / "1.0.json"
        bad.parent.mkdir()
        bad.write_text('{"category": 99}')
        monkeypatch.setattr("pyasteryx.spec.loader._DATA_DIR", tmp_path)
        registry = SpecRegistry.with_bundled()
        assert 99 in registry  # discovery succeeded
        with pytest.raises(SpecificationError, match="missing required key"):
            registry.get(99)


class TestBundledFilesAreMinified:
    def test_no_indentation_is_shipped(self):
        """Indentation was over half the on-disk size of these generated files."""
        for _, _, path in iter_bundled_paths():
            text = path.read_text(encoding="utf-8")
            assert "\n" not in text, f"{path.name} is pretty-printed; regenerate it minified"
            assert ": " not in text and ", " not in text, f"{path.name} has separator padding"

    def test_they_are_still_valid_json_with_the_expected_shape(self):
        for category, edition, path in iter_bundled_paths():
            raw = json.loads(path.read_text(encoding="utf-8"))
            assert raw["category"] == category
            assert raw["edition"] == edition
            assert raw["items"] and raw["uap"]
