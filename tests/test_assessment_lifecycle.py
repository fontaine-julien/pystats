"""Création, essai et figement des évaluations."""

import csv
from dataclasses import replace
import sqlite3

import pytest

from app.assessment_service import (
    assessment_started, clone_assessment, create_assessment, load_assessment_config, update_assessment,
)
from app.config import AssessmentConfig
from app.export import export_analysis_bundle
from app.ui_admin import AdminWindow, AssessmentConfigDialog
from conftest import complete_attempt


def test_edit_lock_and_exact_independent_clone(database):
    db, project, students = database
    source = create_assessment(db, project, "Ancrages", AssessmentConfig(n_scored_items=6))
    config = AssessmentConfig(n_scored_items=6, anchor_count=2, anchor_source_assessment_id=source)
    assessment = create_assessment(db, project, "T0", config, students[:2])
    config = replace(config, n_scored_items=8)
    update_assessment(db, assessment, "T0", config)
    items = db.assessment_items_payload(assessment)
    assert len(items) == 10 and db.verify_assessment_integrity(assessment)
    db.soft_delete_assessment(source, "Ancienne source")
    with pytest.raises(ValueError):
        update_assessment(db, assessment, "Erreur", replace(config, random_seed=9))
    assert db.assessment_items_payload(assessment) == items
    assert load_assessment_config(db, assessment) == config
    attempt = db.create_attempt(assessment, students[0])
    for reason in (None, "teacher_abort"):
        if reason:
            db.finish_attempt(attempt, reason, 0)
        with pytest.raises(ValueError, match="verrouillés"):
            update_assessment(db, assessment, "Autre", config)
    with pytest.raises(sqlite3.IntegrityError, match="started"), db.transaction() as conn:
        conn.execute("UPDATE assessment SET frozen_at=NULL WHERE id=?", (assessment,))
    clone = clone_assessment(db, assessment, "Finale", "2026-06-15", "P5")
    assert db.assessment_items_payload(clone) == items
    assert db.verify_assessment_integrity(clone)
    assert not assessment_started(db, clone)
    assert [r[0] for r in db.q("SELECT student_id FROM assessment_roster WHERE assessment_id=? ORDER BY student_id",
                                (clone,))] == students[:2]
    final_config = replace(config, assessment_date="2026-06-15", academic_period="P5")
    assert load_assessment_config(db, clone) == final_config
    update_assessment(db, clone, "Finale bis", replace(final_config, item_time_limit_s=4))
    assert db.assessment_items_payload(clone) == items
    assert load_assessment_config(db, assessment) == config


def test_rehearse_repeatedly_without_pupil_or_attempt(database, qapp):
    db, project, _ = database
    config = AssessmentConfig(n_scored_items=2, familiarization_enabled=True)
    assessment = create_assessment(db, project, "Préparation", config, [])
    admin = AdminWindow(db)
    admin.assessment_id = assessment
    for finish in (False, True):
        admin.preview_assessment()
        window = admin._student_win
        assert window.ctx.items == db.assessment_items_payload(assessment)
        window._handle_student_key("enter")
        assert window._copy_index == 0
        timer = window._item_timer
        window._handle_student_key("enter")
        window._handle_student_key("skip")
        assert window._copy_index == 0 and window._item_timer is timer
        if finish:
            for trial in window._copy_trials:
                window.answer.setText(trial["target"])
                window._submit_current()
                if trial["phase"] != "measured":
                    window._advance_timer.stop()
                    window._advance_after_feedback()
            window._handle_student_key("enter")
            for item in window.ctx.items:
                window.answer.setText(str(item["expected"]))
                window._submit_current()
                if item["is_practice"]:
                    window._advance_timer.stop()
                    window._advance_after_feedback()
            assert window._result_visible
        window._handle_student_key("escape")
        assert admin.isVisible()
    assert not assessment_started(db, assessment)
    update_assessment(db, assessment, "Prête", config)
    admin.close()


def test_settings_roundtrip_and_readonly(database, qapp):
    config = AssessmentConfig(operations=("division", "addition"), operand_1_values=(4, 1, 3),
                              familiarization_enabled=True, allow_omissions=True, random_seed=123, item_time_limit_s=1.25,
                              anchor_source_assessment_id=9, anchor_count=1)
    dialog = AssessmentConfigDialog(None, [], title="T0", config=config)
    dialog._validate_and_accept()
    assert dialog.result_config() == ("T0", config)
    locked = AssessmentConfigDialog(None, [], title="T0", config=config, locked=True)
    assert locked.seed.text() == "123" and not locked.seed.isEnabled()
    locked.close()


def test_exports_exclude_aborts_open_attempts_and_absentees(database, tmp_path):
    db, project, students = database
    assessment = create_assessment(db, project, "T0", AssessmentConfig(n_scored_items=3, familiarization_enabled=True))
    valid = complete_attempt(db, assessment, students[0])
    for pupil in students[:2]:
        db.finish_attempt(db.create_attempt(assessment, pupil), "teacher_abort", 100)
    db.create_attempt(assessment, students[2])
    timed = db.create_attempt(assessment, students[3])
    db.finish_attempt(timed, "global_time_limit", 300)
    used = {r[0] for r in db.q("SELECT attempt_uuid FROM attempt WHERE id IN (?,?)", (valid, timed))}
    outputs = export_analysis_bundle(db, str(tmp_path / "export"), assessment, True)
    for name in ("responses", "students", "familiarization_trials", "familiarization_summary",
                 "nominative_internal", "nominative_student_summary_internal"):
        with open(outputs[name], encoding="utf-8", newline="") as stream:
            assert {row["attempt_id"] for row in csv.DictReader(stream)} == used
