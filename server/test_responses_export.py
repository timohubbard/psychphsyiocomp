"""Answers to on-screen questions in the export — and typed ones kept out unless asked.

A typed answer is the one field where a participant can write their name. The
rest of the data is pseudonymised before any write; a text box is not, so the
export withholds it by default and the audit refuses an archive where it leaks.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest

import export
from alignment import ClockSolution
from engine_contract import Chunk, EventRow
from study import content_hash
from tables import CanonicalWriter, SessionContext

MASTER = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0,
                       uncertainty_ms=0.0, n_anchors=0)
STUDY = {
    "study_id": "qs", "name": "Q", "version": "1.0.0",
    "disclosure": {"retention_days": 30, "secondary_use": "Team only.", "contact": "a@b.ac.uk",
                   "free_text": True},
    "consent_tiers": ["features_only"], "modalities": ["face"],
    "tasks": [{"type": "questions", "id": "after", "items": [
        {"id": "pleasant", "kind": "likert", "prompt": "How pleasant?", "points": 7, "anchors": ["no", "yes"]},
        {"id": "notes", "kind": "text", "prompt": "Anything else?", "allow_skip": True}]}],
}
SECRET = "My name is Jane Example and I take lithium"


@pytest.fixture
def out(tmp_path):
    o = tmp_path / "out"
    w = CanonicalWriter(o, SessionContext("s1", "p_x", "qs"))
    w.set_session_metadata({"study": {"study_id": "qs", "study_content_hash": content_hash(STUDY),
                                      "audience": "participants"}})
    resp = lambda t, meta: EventRow(event_type="response", native_clock_id="performance.now",  # noqa: E731
                                    onset_native_ts=t, offset_native_ts=None, stimulus_id=None, metadata=meta)
    w.add_chunks([Chunk(events=(
        resp(1000.0, {"task_id": "after", "item_id": "pleasant", "kind": "likert", "value": 6,
                      "rt_ms": 1840, "n_changes": 2, "skipped": False}),
        resp(5000.0, {"task_id": "after", "item_id": "notes", "kind": "text", "value_text": SECRET,
                      "rt_ms": 9000, "n_changes": 30, "skipped": False}),
    ))], source="capture@0.1.0+browser", params={}, solution=MASTER)
    w.close()
    return o


def _zip(out, tmp_path, **kw):
    z = tmp_path / "x.zip"
    export.build(out, STUDY, z, **kw)
    with zipfile.ZipFile(z) as f:
        return {n: f.read(n) for n in f.namelist()}


def test_answers_are_exported_one_row_per_question(out, tmp_path):
    files = _zip(out, tmp_path)
    rows = list(csv.DictReader(io.StringIO(files["csv/responses.csv"].decode())))
    by = {r["item_id"]: r for r in rows}
    assert by["pleasant"]["value"] == "6" and by["pleasant"]["rt_ms"] == "1840"
    assert by["pleasant"]["n_changes"] == "2" and by["pleasant"]["skipped"] == "False"


def test_typed_answers_are_withheld_from_every_file_by_default(out, tmp_path):
    files = _zip(out, tmp_path)
    for name, data in files.items():
        assert b"Jane Example" not in data, name
    rows = {r["item_id"]: r for r in csv.DictReader(io.StringIO(files["csv/responses.csv"].decode()))}
    assert rows["notes"]["value_text_withheld"] == "True" and rows["notes"]["value_text"] == ""
    assert b"withheld" in files["provenance.json"]


def test_typed_answers_are_included_only_when_asked(out, tmp_path):
    files = _zip(out, tmp_path, include_free_text=True)
    rows = {r["item_id"]: r for r in csv.DictReader(io.StringIO(files["csv/responses.csv"].decode()))}
    assert rows["notes"]["value_text"] == SECRET


def test_the_audit_refuses_an_archive_where_a_typed_answer_leaked(out):
    with pytest.raises(export.ExportRefused, match="typed answer"):
        export._audit({"csv/x.csv": f"note,{SECRET}".encode()}, out, withheld={SECRET})
