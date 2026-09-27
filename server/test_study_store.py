"""The builder's write paths: a used study is fixed, a stimulus is its hash."""

from __future__ import annotations

import hashlib
import json

import pytest

import study_store
from study import validate_study
from tables import CanonicalWriter, SessionContext


def study(sid="draft", **over):
    s = {"study_id": sid, "name": "Draft", "version": "1.0.0",
         "disclosure": {"retention_days": 30, "secondary_use": "Team only.",
                        "contact": "a.researcher@uni.ac.uk"},
         "consent_tiers": ["features_only"], "default_tier": "features_only",
         "modalities": ["face"], "tasks": [{"type": "rest_fixation", "duration_ms": 5000}]}
    s.update(over)
    return s


@pytest.fixture
def roots(tmp_path):
    studies, out = tmp_path / "studies", tmp_path / "out"
    studies.mkdir()
    (studies / "index.json").write_text(json.dumps({"studies": ["m0"]}))
    return studies, out


def record_session(out, sid, study_id):
    w = CanonicalWriter(out, SessionContext(sid, "p", study_id))
    w.set_session_metadata({})
    w.close()


def test_a_valid_study_is_written_and_indexed(roots):
    studies, out = roots
    r = study_store.save_study(studies, out, study())
    saved = json.loads((studies / "draft.json").read_text(encoding="utf-8"))
    assert validate_study(saved).ok and r["content_hash"]
    assert json.loads((studies / "index.json").read_text())["studies"] == ["m0", "draft"]


def test_an_invalid_study_is_refused_with_its_reasons(roots):
    studies, out = roots
    with pytest.raises(study_store.StoreRefused) as e:
        study_store.save_study(studies, out, study(audience="participants"))
    assert e.value.status == 400
    assert any("irb_reference" in r for r in e.value.extra["reasons"])
    assert not (studies / "draft.json").exists()


def test_a_draft_is_overwritten_only_when_asked(roots):
    studies, out = roots
    study_store.save_study(studies, out, study())
    with pytest.raises(study_store.StoreRefused) as e:
        study_store.save_study(studies, out, study(name="Renamed"))
    assert e.value.status == 409 and e.value.extra["can_overwrite"]
    study_store.save_study(studies, out, study(name="Renamed"), overwrite=True)
    assert json.loads((studies / "draft.json").read_text())["name"] == "Renamed"
    assert json.loads((studies / "index.json").read_text())["studies"].count("draft") == 1


def test_a_study_with_sessions_is_fixed_even_when_overwrite_is_asked(roots):
    """Editing it would make every session under it report an edited protocol."""
    studies, out = roots
    study_store.save_study(studies, out, study())
    record_session(out, "s1", "draft")
    before = (studies / "draft.json").read_bytes()
    with pytest.raises(study_store.StoreRefused) as e:
        study_store.save_study(studies, out, study(name="Edited"), overwrite=True)
    assert e.value.status == 409
    assert e.value.extra["sessions"] == ["s1"] and e.value.extra["suggestion"] == "draft-v2"
    assert (studies / "draft.json").read_bytes() == before


def test_a_stimulus_is_stored_with_its_hash_and_kind(roots):
    studies, _ = roots
    r = study_store.save_stimulus(studies, "forest.png", b"\x89PNG fake")
    assert r == {"src": "stimuli/forest.png", "sha256": hashlib.sha256(b"\x89PNG fake").hexdigest(),
                 "kind": "image", "bytes": 9}
    assert study_store.save_stimulus(studies, "clip.webm", b"x")["kind"] == "video"


def test_a_stimulus_cannot_be_replaced_by_different_bytes(roots):
    studies, _ = roots
    study_store.save_stimulus(studies, "forest.png", b"one")
    assert study_store.save_stimulus(studies, "forest.png", b"one")["bytes"] == 3, "same bytes: no-op"
    with pytest.raises(study_store.StoreRefused) as e:
        study_store.save_stimulus(studies, "forest.png", b"two")
    assert e.value.status == 409
    assert (studies / "stimuli" / "forest.png").read_bytes() == b"one"


@pytest.mark.parametrize("name", ["../escape.png", "a/b.png", "notes.txt", ".hidden.png", ""])
def test_stimulus_names_and_types_are_refused(roots, name):
    studies, _ = roots
    with pytest.raises(study_store.StoreRefused):
        study_store.save_stimulus(studies, name, b"x")
    assert not any(p.name == "escape.png" for p in studies.parent.rglob("*"))
