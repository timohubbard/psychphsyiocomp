"""Tests for AOI definition persistence and its versioning rules."""

from __future__ import annotations

import json

import pytest

import aoi_store
from aoi import AOI, AOISet

A = AOI("left", "rect", (0.0, 0.0, 0.4, 1.0), label="left panel")
B = AOI("right", "rect", (0.6, 0.0, 1.0, 1.0), label="right panel")
SET = AOISet("panels", "pending", (A, B))


def test_saving_a_new_set_writes_version_one(tmp_path):
    r = aoi_store.save(tmp_path, SET)
    assert r["written"] is True
    assert r["version"] == "1"
    assert r["n_aois"] == 2


def test_saving_an_unchanged_set_is_a_no_op(tmp_path):
    """Clicking save twice must not create history implying a change of mind."""
    aoi_store.save(tmp_path, SET)
    again = aoi_store.save(tmp_path, SET)
    assert again["written"] is False
    assert again["reason"] == "unchanged"
    assert len(aoi_store.history(tmp_path, "panels")) == 1


def test_changing_a_boundary_writes_a_new_version_beside_the_old(tmp_path):
    """§4.2: hit rates moved 77% -> 88% -> 93% purely from refining the same
    definitions on the same data. Refinement is legitimate and expected — but if
    editing replaced the set, every number computed under the old boundaries
    would become unreproducible and unattributable.
    """
    aoi_store.save(tmp_path, SET)
    wider = AOISet("panels", "pending", (AOI("left", "rect", (0.0, 0.0, 0.45, 1.0)), B))
    r = aoi_store.save(tmp_path, wider)

    assert r["written"] is True
    assert r["version"] == "2"

    versions = aoi_store.history(tmp_path, "panels")
    assert [v["version"] for v in versions] == ["1", "2"]
    assert versions[0]["content_hash"] != versions[1]["content_hash"]


def test_the_old_version_is_still_loadable_after_a_revision(tmp_path):
    """The whole point of keeping history: an old result stays attributable."""
    aoi_store.save(tmp_path, SET)
    aoi_store.save(tmp_path, AOISet("panels", "pending",
                                    (AOI("left", "rect", (0.0, 0.0, 0.45, 1.0)), B)))

    old = aoi_store.load(tmp_path, "panels", version="1")
    assert old.aois[0].coords == (0.0, 0.0, 0.4, 1.0)


def test_loading_without_a_version_gives_the_newest(tmp_path):
    aoi_store.save(tmp_path, SET)
    aoi_store.save(tmp_path, AOISet("panels", "pending",
                                    (AOI("left", "rect", (0.0, 0.0, 0.45, 1.0)), B)))
    assert aoi_store.load(tmp_path, "panels").version == "2"


def test_round_trip_preserves_geometry_and_identity(tmp_path):
    aoi_store.save(tmp_path, SET)
    loaded = aoi_store.load(tmp_path, "panels")

    assert {a.aoi_id for a in loaded.aois} == {"left", "right"}
    assert loaded.aois[0].label == "left panel"
    # Identity survives the file, which is what makes a recorded hash useful.
    assert loaded.content_hash() == AOISet("panels", "1", (A, B)).content_hash()


def test_each_saved_file_restates_why_the_boundaries_matter(tmp_path):
    """Someone reading one of these years later needs to know the boundaries are
    part of any result computed from them."""
    r = aoi_store.save(tmp_path, SET)
    raw = json.loads((tmp_path / "aoi_sets" / r["file"]).read_text(encoding="utf-8"))
    assert "77" in raw["note"] and "padding" in raw["note"]


def test_loading_an_unknown_set_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        aoi_store.load(tmp_path, "nope")


def test_loading_an_unknown_version_raises(tmp_path):
    aoi_store.save(tmp_path, SET)
    with pytest.raises(FileNotFoundError):
        aoi_store.load(tmp_path, "panels", version="7")


def test_listing_an_empty_root_returns_nothing(tmp_path):
    assert aoi_store.list_sets(tmp_path) == []
    assert aoi_store.history(tmp_path, "panels") == []


def test_a_corrupt_file_is_skipped_rather_than_crashing_the_listing(tmp_path):
    """One bad file must not make every other set unreachable."""
    aoi_store.save(tmp_path, SET)
    (tmp_path / "aoi_sets" / "broken.json").write_text("{not json", encoding="utf-8")
    assert [r["name"] for r in aoi_store.list_sets(tmp_path)] == ["panels"]


def test_names_with_path_separators_cannot_escape_the_store(tmp_path):
    """The name reaches this from an HTTP body."""
    aoi_store.save(tmp_path, AOISet("../../evil", "pending", (A,)))
    written = list((tmp_path / "aoi_sets").glob("*.json"))
    assert len(written) == 1
    assert written[0].parent == tmp_path / "aoi_sets"
