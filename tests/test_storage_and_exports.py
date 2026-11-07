"""Stockage des réponses, séparation des identités et exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3

import pytest

from app.export import export_analysis_bundle
from app.graph import generate_analysis_outputs
from conftest import complete_attempt, create_sample_assessment, timing_result


def test_false_omission_timeout_interruption_and_double_save(database) -> None:
    db, project_id, student_ids = database
    assessment_id = create_sample_assessment(db, project_id, student_ids)
    attempt_id = db.create_attempt(assessment_id, student_ids[0])
    items = db.load_attempt_items(attempt_id)
    scored = [item for item in items if item["evaluated"]]
    first = scored[0]
    db.save_response(first["attempt_item_id"], 999, False, "999", timing_result(), "answered")
    with pytest.raises(RuntimeError, match="déjà été enregistrée"):
        db.save_response(first["attempt_item_id"], 999, False, "999", timing_result(), "answered")
    db.save_response(scored[1]["attempt_item_id"], None, None, "", timing_result(text=""), "omission")
    db.save_response(scored[2]["attempt_item_id"], None, None, "", timing_result(text=""), "timeout", "item")
    db.save_response(scored[3]["attempt_item_id"], None, None, "", timing_result(text=""), "interrupted")
    db.finish_attempt(attempt_id, "teacher_abort", 4000)
    attempt = db.q("SELECT * FROM attempt WHERE id=?", (attempt_id,))[0]
    assert attempt["items_incorrect"] == 1
    assert attempt["items_omitted"] == 1
    assert attempt["items_timeout"] == 1
    assert attempt["items_not_presented"] == 2
    response_id = db.q("SELECT id FROM attempt_response WHERE attempt_item_id=?", (first["attempt_item_id"],))[0]["id"]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.exec("UPDATE attempt_response SET answer=1 WHERE id=?", (response_id,))


def test_exports_have_correct_median_and_no_names(database, tmp_path: Path) -> None:
    db, project_id, student_ids = database
    first_assessment = create_sample_assessment(db, project_id, student_ids, seed=1, date="2026-01-15")
    for offset, student_id in enumerate(student_ids):
        complete_attempt(db, first_assessment, student_id, offset)
    second_assessment = create_sample_assessment(
        db, project_id, student_ids, seed=2, date="2026-03-15", source_id=first_assessment
    )
    for offset, student_id in enumerate(student_ids):
        complete_attempt(db, second_assessment, student_id, offset)
    outputs = export_analysis_bundle(db, str(tmp_path / "exports"), include_nominative_internal=True, organized=True)
    assert Path(outputs["public"]).parent.name == "Publication"
    assert Path(outputs["items"]).parent == tmp_path / "exports" / "Publication" / "data"
    assert Path(outputs["nominative_internal"]).parent.name == "Enseignant"
    analytical_paths = [path for key, path in outputs.items() if "nominative" not in key]
    analytical_text = "\n".join(Path(path).read_text(encoding="utf-8") for path in analytical_paths)
    assert "NOM1" not in analytical_text
    assert "Prenom1" not in analytical_text
    assert "NOM1" in Path(outputs["nominative_internal"]).read_text(encoding="utf-8")
    assert "NOM1" in Path(outputs["nominative_student_summary_internal"]).read_text(encoding="utf-8")
    with Path(outputs["students"]).open(encoding="utf-8", newline="") as stream:
        summaries = list(csv.DictReader(stream))
    assert summaries
    assert all(row["median_correct_time_ms"] for row in summaries)
    public_text = Path(outputs["public"]).read_text(encoding="utf-8")
    assert "STU-" not in public_text
    assert "2026-01-15" not in public_text


def test_pseudonym_is_stable_across_reopen(database) -> None:
    db, _, student_ids = database
    database_path = str(db.path)
    first_id = str(db.get_student_identity(student_ids[0])["export_id"])
    db.close()
    db.open(database_path)
    assert db.get_student_identity(student_ids[0])["export_id"] == first_id


def test_assessment_soft_delete_retains_data_reason_and_audit(database, tmp_path: Path) -> None:
    db, project_id, student_ids = database
    assessment_id = create_sample_assessment(db, project_id, student_ids)
    complete_attempt(db, assessment_id, student_ids[0])
    attempt_count = db.q("SELECT count(*) AS n FROM attempt WHERE assessment_id=?", (assessment_id,))[0]["n"]
    response_count = db.q(
        "SELECT count(*) AS n FROM attempt_response ar JOIN attempt_item ai ON ai.id=ar.attempt_item_id "
        "JOIN attempt att ON att.id=ai.attempt_id WHERE att.assessment_id=?",
        (assessment_id,),
    )[0]["n"]

    deleted_at = db.soft_delete_assessment(assessment_id, "Erreur de paramétrage constatée après la passation")
    assessment = db.q("SELECT * FROM assessment WHERE id=?", (assessment_id,))[0]
    assert assessment["deleted_at"] == deleted_at
    assert assessment["deletion_reason"] == "Erreur de paramétrage constatée après la passation"
    assert assessment_id not in {int(row["id"]) for row in db.list_assessments(project_id)}
    assert assessment_id in {int(row["id"]) for row in db.list_assessments(project_id, include_deleted=True)}
    assert db.q("SELECT count(*) AS n FROM attempt WHERE assessment_id=?", (assessment_id,))[0]["n"] == attempt_count
    assert db.q(
        "SELECT count(*) AS n FROM attempt_response ar JOIN attempt_item ai ON ai.id=ar.attempt_item_id "
        "JOIN attempt att ON att.id=ai.attempt_id WHERE att.assessment_id=?",
        (assessment_id,),
    )[0]["n"] == response_count
    audit_row = db.q(
        "SELECT occurred_at,details_json FROM audit_event WHERE event_type='assessment_deleted' AND entity_id=?",
        (str(assessment_id),),
    )[0]
    details = json.loads(audit_row["details_json"])
    assert audit_row["occurred_at"] == deleted_at
    assert details["reason"] == assessment["deletion_reason"]
    assert details["retention_mode"] == "soft_delete"
    with pytest.raises(RuntimeError, match="supprimée"):
        db.create_attempt(assessment_id, student_ids[1])
    outputs = export_analysis_bundle(db, str(tmp_path / "after_delete"))
    assert assessment["assessment_uuid"] not in Path(outputs["responses"]).read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="motif"):
        db.soft_delete_assessment(assessment_id, "")


def test_export_respects_explicit_assessment_selection(database, tmp_path: Path) -> None:
    db, project_id, student_ids = database
    first_id = create_sample_assessment(db, project_id, student_ids, seed=10, date="2026-01-10")
    second_id = create_sample_assessment(db, project_id, student_ids, seed=20, date="2026-02-10")
    for student_id in student_ids:
        complete_attempt(db, first_id, student_id)
        complete_attempt(db, second_id, student_id)
    second_uuid = str(db.q("SELECT assessment_uuid FROM assessment WHERE id=?", (second_id,))[0]["assessment_uuid"])
    first_uuid = str(db.q("SELECT assessment_uuid FROM assessment WHERE id=?", (first_id,))[0]["assessment_uuid"])
    outputs = export_analysis_bundle(
        db,
        str(tmp_path / "selected"),
        assessment_ids=[second_id],
    )
    response_text = Path(outputs["responses"]).read_text(encoding="utf-8")
    assert second_uuid in response_text
    assert first_uuid not in response_text


def test_pupil_removal_rename_and_named_charts(database, tmp_path, monkeypatch):
    from app.dashboard_data import build_snapshot
    db, project, pupils = database
    assessment = create_sample_assessment(db, project, pupils)
    for pupil in pupils:
        complete_attempt(db, assessment, pupil)
    db.rename_student(pupils[1], "NOM-CORRIGÉ", "Prénom composé")
    assert len(build_snapshot(db.path, project, use_cache=True).results) == 6
    db.remove_student(pupils[0])
    snap = build_snapshot(db.path, project, use_cache=True)
    assert len(snap.results) == 5 and pupils[0] not in snap.roster[assessment]
    assert len(db.list_students(project)) == 5
    assert not db.q("SELECT id FROM attempt WHERE student_id=?", (pupils[0],))
    assert db.get_student_identity(pupils[0]) is None
    monkeypatch.setenv("PYSTATS_BOOTSTRAP_REPLICATES", "100")
    outputs = generate_analysis_outputs(db, assessment, str(tmp_path / "analysis"), include_nominative_final_labels=True)
    root = Path(outputs["output_dir"])
    for view, expected in [(root / "Enseignant", True), (root / "Publication/results", False)]:
        assert (view / "figures/01_heatmap_students_items.png").is_file()
        assert ("NOM-CORRIGÉ Prénom composé" in (view / "student_speed_accuracy_interactive.html").read_text("utf-8")) == expected
        assert len(list((view / "individual_reports").glob("*.pdf"))) == 5
    assert not (root / "Enseignant/figures/07_item_difficulty.png").exists()
