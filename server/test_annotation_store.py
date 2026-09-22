"""Tests for the annotation store.

Most of these are about isolation between raters. The whole value of a human
reference standard is that you can measure how much the humans disagreed, and
every way of losing that is silent: merging raters at write time, serving one
coder another's labels, or filling a skipped item with the majority. None of
those raise; they just make the ceiling read higher than it is.
"""

from __future__ import annotations

import json

import pytest

from annotation_store import (
    codebook_hash,
    label_matrix,
    list_codebooks,
    load_annotation,
    load_codebook,
    raters_for,
    save_annotation,
    save_codebook,
    validate_codebook,
)


def codebook(**over):
    base = {
        "codebook_id": "looking-at",
        "name": "Where is the participant looking?",
        "categories": [
            {"id": "screen", "label": "At the screen",
             "description": "Eyes directed at the monitor."},
            {"id": "away", "label": "Away",
             "description": "Eyes directed anywhere other than the monitor."},
            {"id": "closed", "label": "Eyes closed",
             "description": "Both eyelids fully closed, including a blink."},
        ],
        "items": [1000.0, 2000.0, 3000.0, 4000.0],
    }
    base.update(over)
    return base


@pytest.fixture
def root(tmp_path):
    save_codebook(tmp_path, codebook())
    return tmp_path


def saved_hash(root):
    return load_codebook(root, "looking-at")["content_hash"]


def submit(root, rater, labels):
    return save_annotation(root, codebook_id="looking-at",
                           content_hash=saved_hash(root),
                           session_id="s001", rater_id=rater, labels=labels)


ALL_SCREEN = {"1000.0": "screen", "2000.0": "screen",
              "3000.0": "screen", "4000.0": "screen"}


# ---------------------------------------------------------------------------
# codebooks
# ---------------------------------------------------------------------------

def test_a_complete_codebook_validates():
    assert validate_codebook(codebook()) == (True, [])


def test_one_category_is_not_a_decision():
    """A coder who can only say 'present' produces labels with no variance,
    and every agreement coefficient over them is undefined."""
    ok, reasons = validate_codebook(codebook(categories=[
        {"id": "present", "label": "Present", "description": "It happened."}]))
    assert not ok
    assert any("at least two categories" in r for r in reasons)


def test_a_category_without_a_description_is_refused():
    """Not pedantry: an undefined category is where coders silently diverge,
    and it surfaces later as a low kappa nobody can explain."""
    ok, reasons = validate_codebook(codebook(categories=[
        {"id": "a", "label": "A", "description": "Defined."},
        {"id": "b", "label": "B", "description": "  "}]))
    assert not ok
    assert any("silently disagree" in r for r in reasons)


def test_duplicate_category_ids_are_refused():
    ok, reasons = validate_codebook(codebook(categories=[
        {"id": "a", "label": "A", "description": "x"},
        {"id": "a", "label": "Also A", "description": "y"}]))
    assert any("duplicate" in r for r in reasons)


def test_a_codebook_with_nothing_to_annotate_is_refused():
    assert not validate_codebook(codebook(items=[]))[0]


def test_changing_a_category_description_changes_the_hash():
    """'Present' means something different once the definition of present
    changes, so labels made under the old wording are not comparable."""
    a = codebook()
    b = codebook(categories=[
        dict(a["categories"][0], description="Eyes within the monitor bezel."),
        *a["categories"][1:]])
    assert codebook_hash(a) != codebook_hash(b)


def test_renaming_the_codebook_does_not_change_the_hash():
    assert codebook_hash(codebook()) == codebook_hash(codebook(name="Gaze coding"))


def test_reordering_categories_does_not_change_the_hash():
    cats = codebook()["categories"]
    assert codebook_hash(codebook()) == codebook_hash(
        codebook(categories=list(reversed(cats))))


def test_saving_an_unchanged_codebook_does_not_make_a_second_version(root):
    first = load_codebook(root, "looking-at")
    again = save_codebook(root, codebook())
    assert again["created_utc"] == first["created_utc"]
    assert len(list_codebooks(root)) == 1


def test_changing_a_codebook_keeps_the_old_version(root):
    save_codebook(root, codebook(items=[1000.0, 2000.0]))
    assert len(list_codebooks(root)) == 2


def test_an_invalid_codebook_is_not_written(root):
    with pytest.raises(ValueError):
        save_codebook(root, codebook(categories=[]))
    assert len(list_codebooks(root)) == 1


# ---------------------------------------------------------------------------
# raters stay apart
# ---------------------------------------------------------------------------

def test_two_raters_are_stored_separately(root):
    submit(root, "r1", ALL_SCREEN)
    submit(root, "r2", {**ALL_SCREEN, "2000.0": "away"})

    a = load_annotation(root, codebook_id="looking-at", content_hash=saved_hash(root),
                        session_id="s001", rater_id="r1")
    b = load_annotation(root, codebook_id="looking-at", content_hash=saved_hash(root),
                        session_id="s001", rater_id="r2")
    assert a["labels"]["2000.0"] == "screen"
    assert b["labels"]["2000.0"] == "away"


def test_a_rater_resubmitting_replaces_only_their_own_work(root):
    submit(root, "r1", ALL_SCREEN)
    submit(root, "r2", {**ALL_SCREEN, "2000.0": "away"})
    submit(root, "r1", {**ALL_SCREEN, "1000.0": "closed"})

    b = load_annotation(root, codebook_id="looking-at", content_hash=saved_hash(root),
                        session_id="s001", rater_id="r2")
    assert b["labels"]["2000.0"] == "away", "r1's revision touched r2's file"


def test_progress_is_visible_without_the_labels(root):
    """A coordinator needs to know whether a second rater finished. That is
    not contamination; the labels are."""
    submit(root, "r1", ALL_SCREEN)
    submit(root, "r2", {"1000.0": "screen"})

    rows = raters_for(root, codebook_id="looking-at",
                      content_hash=saved_hash(root), session_id="s001")
    by_id = {r["rater_id"]: r for r in rows}
    assert by_id["r1"]["complete"] is True
    assert by_id["r2"]["complete"] is False
    assert by_id["r2"]["n_labelled"] == 1
    assert all("labels" not in r for r in rows)


def test_sessions_do_not_leak_into_each_other(root):
    submit(root, "r1", ALL_SCREEN)
    save_annotation(root, codebook_id="looking-at", content_hash=saved_hash(root),
                    session_id="s002", rater_id="r1", labels=ALL_SCREEN)
    rows = raters_for(root, codebook_id="looking-at",
                      content_hash=saved_hash(root), session_id="s001")
    assert len(rows) == 1


def test_codebook_versions_do_not_share_annotations(root):
    submit(root, "r1", ALL_SCREEN)
    v2 = save_codebook(root, codebook(items=[1000.0, 2000.0]))
    rows = raters_for(root, codebook_id="looking-at",
                      content_hash=v2["content_hash"], session_id="s001")
    assert rows == []


# ---------------------------------------------------------------------------
# what a submission may contain
# ---------------------------------------------------------------------------

def test_a_label_outside_the_codebook_is_refused(root):
    with pytest.raises(ValueError, match="not in this codebook"):
        submit(root, "r1", {**ALL_SCREEN, "1000.0": "asleep"})


def test_a_label_for_an_item_the_codebook_does_not_have_is_refused(root):
    with pytest.raises(ValueError, match="items not in this codebook"):
        submit(root, "r1", {**ALL_SCREEN, "9999.0": "screen"})


def test_an_empty_submission_is_refused(root):
    with pytest.raises(ValueError):
        submit(root, "r1", {})


def test_a_rater_id_that_traverses_is_refused(root):
    with pytest.raises(ValueError, match="rater_id"):
        save_annotation(root, codebook_id="looking-at",
                        content_hash=saved_hash(root), session_id="s001",
                        rater_id="../../etc/passwd", labels=ALL_SCREEN)


def test_a_partial_submission_is_allowed_and_marked(root):
    """Coding is long work and a coder should be able to stop. What must not
    happen is a partial set being read as a complete one."""
    rec = submit(root, "r1", {"1000.0": "screen", "2000.0": "away"})
    assert rec["complete"] is False
    assert rec["n_labelled"] == 2
    assert rec["n_items"] == 4


def test_nothing_is_returned_for_a_rater_who_has_not_started(root):
    assert load_annotation(root, codebook_id="looking-at",
                           content_hash=saved_hash(root),
                           session_id="s001", rater_id="nobody") is None


# ---------------------------------------------------------------------------
# the matrix evaluation reads
# ---------------------------------------------------------------------------

def test_the_matrix_aligns_raters_on_shared_items(root):
    submit(root, "r1", ALL_SCREEN)
    submit(root, "r2", {**ALL_SCREEN, "3000.0": "away"})

    m = label_matrix(root, codebook_id="looking-at",
                     content_hash=saved_hash(root), session_id="s001")
    assert m["raters"] == ["r1", "r2"]
    assert m["items"] == ["1000.0", "2000.0", "3000.0", "4000.0"]
    assert m["labels"][0][2] == "screen"
    assert m["labels"][1][2] == "away"


def test_an_item_one_rater_skipped_is_dropped_not_imputed(root):
    """Filling it with the majority would manufacture agreement out of
    someone's uncertainty, inflating the exact ceiling the reference standard
    exists to measure honestly."""
    submit(root, "r1", ALL_SCREEN)
    submit(root, "r2", {"1000.0": "screen", "2000.0": "screen",
                        "4000.0": "screen"})

    m = label_matrix(root, codebook_id="looking-at",
                     content_hash=saved_hash(root), session_id="s001")
    assert "3000.0" not in m["items"]
    assert m["n_dropped"] == 1
    assert all(len(row) == 3 for row in m["labels"])


def test_the_matrix_is_empty_rather_than_broken_with_no_raters(root):
    m = label_matrix(root, codebook_id="looking-at",
                     content_hash=saved_hash(root), session_id="s001")
    assert m["raters"] == [] and m["labels"] == []


def test_the_matrix_carries_the_codebook_version_it_was_built_from(root):
    submit(root, "r1", ALL_SCREEN)
    m = label_matrix(root, codebook_id="looking-at",
                     content_hash=saved_hash(root), session_id="s001")
    assert m["codebook_content_hash"] == saved_hash(root)


def test_the_matrix_feeds_the_evaluation_module(root):
    """The join the whole store exists for."""
    from evaluation import reference_from

    many = [float(i * 100) for i in range(60)]
    save_codebook(root, codebook(codebook_id="long", items=many))
    h = load_codebook(root, "long")["content_hash"]

    a = {str(t): ("screen" if i % 3 else "away") for i, t in enumerate(many)}
    b = dict(a)
    b[str(many[0])] = "closed"

    for rater, labels in (("r1", a), ("r2", b)):
        save_annotation(root, codebook_id="long", content_hash=h,
                        session_id="s001", rater_id=rater, labels=labels)

    m = label_matrix(root, codebook_id="long", content_hash=h, session_id="s001")
    ref = reference_from(m["labels"], use="raw")
    assert ref.n_raters == 2
    assert ref.ceiling > 0.9


def test_a_single_rater_still_produces_a_matrix_but_no_reference(root):
    """The store records what exists; refusing to call it a reference standard
    is `evaluation.py`'s job, and it does."""
    from evaluation import Refusal, reference_from

    many = [float(i * 100) for i in range(60)]
    save_codebook(root, codebook(codebook_id="solo", items=many))
    h = load_codebook(root, "solo")["content_hash"]
    save_annotation(root, codebook_id="solo", content_hash=h, session_id="s001",
                    rater_id="r1",
                    labels={str(t): "screen" for t in many})

    m = label_matrix(root, codebook_id="solo", content_hash=h, session_id="s001")
    assert len(m["raters"]) == 1
    assert isinstance(reference_from(m["labels"]), Refusal)


def test_stored_files_do_not_record_who_the_coder_is(root):
    """Coders are people too. A slug the researcher assigns, never a name."""
    submit(root, "r1", ALL_SCREEN)
    files = list((root / "annotations").rglob("*.json"))
    blob = json.loads(files[0].read_text(encoding="utf-8"))
    assert set(blob) == {
        "codebook_id", "codebook_content_hash", "session_id", "rater_id",
        "labels", "n_items", "n_labelled", "complete", "submitted_utc"}


def test_changing_the_items_changes_the_hash():
    """The hash is the directory annotations are filed under. If two codebook
    versions covering different moments shared it, two raters who coded
    different sets would be pooled as though they had coded the same ones —
    and every agreement coefficient over that is meaningless while nothing
    about it looks wrong."""
    assert codebook_hash(codebook()) != codebook_hash(
        codebook(items=[1000.0, 2000.0]))


def test_reordering_the_items_changes_the_hash():
    """The order a coder sees moments in is part of the protocol, for the same
    reason calibration order is."""
    assert codebook_hash(codebook()) != codebook_hash(
        codebook(items=[4000.0, 3000.0, 2000.0, 1000.0]))
