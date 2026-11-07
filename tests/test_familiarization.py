"""Indépendance de la familiarisation et du score de calcul."""

from __future__ import annotations

import csv
from dataclasses import replace
import json
import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.assessment_service import create_assessment, load_assessment_config
from app.config import AssessmentConfig
from app.export import export_analysis_bundle
from app.familiarization import copy_trials
from app.ui_admin import AdminWindow, AssessmentConfigDialog
from app.ui_keyboard_training import KeyboardTrainingWindow
from app.ui_student import StudentContext, StudentWindow
from conftest import complete_attempt, timing_result


def create_copy_assessment(database, enabled=True):
    db, project, students = database
    config = AssessmentConfig(n_scored_items=6, familiarization_enabled=enabled)
    assessment = create_assessment(db, project, "Copie test", config, students)
    return assessment


def pupil_window(database, enabled=True):
    db, _, students = database
    assessment = create_copy_assessment(database, enabled)
    attempt = db.create_attempt(assessment, students[0])
    context = StudentContext(
        attempt, students[0], "Élève test", "Test", [dict(r) for r in db.load_attempt_items(attempt)],
        0.001, 0.001,
    )
    window = StudentWindow(db, context, lambda: None)
    window.show()
    QApplication.processEvents()
    return window


def enter_number(widget, text):
    for digit in text:
        QTest.keyClick(widget, getattr(Qt, f"Key_{digit}"), Qt.KeypadModifier)
    QTest.keyClick(widget, Qt.Key_Enter, Qt.KeypadModifier)


def csv_rows(path):
    with open(path, encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_config_and_dialog_are_opt_in_and_frozen(database, qapp):
    assert not AssessmentConfig.from_dict({}).familiarization_enabled
    dialog = AssessmentConfigDialog(None, [])
    assert not dialog.familiarization.isChecked()
    dialog.title.setText("Avec clavier")
    dialog.familiarization.setChecked(True)
    dialog._validate_and_accept()
    assert dialog.result_config()[1].familiarization_enabled
    db, project, students = database
    config = dialog.result_config()[1]
    with_copy = create_assessment(db, project, "Avec", config, students)
    without_copy = create_assessment(db, project, "Sans", replace(config, familiarization_enabled=False), students)
    assert load_assessment_config(db, with_copy).familiarization_enabled
    assert db.assessment_items_payload(with_copy) == db.assessment_items_payload(without_copy)
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        db.exec("UPDATE assessment SET config_json='{}' WHERE id=?", (with_copy,))
    measured = [t for t in copy_trials() if t.phase == "measured"]
    assert len(measured) == 12
    assert sum(len(t.target) == 1 for t in measured) == 6
    assert set("".join(t.target for t in measured)) == set("0123456789")
    dialog.close()


def test_exports_keep_missing_optional_values_and_identical_scores(database, tmp_path):
    db, _, students = database
    enabled = create_copy_assessment(database)
    disabled = create_copy_assessment(database, False)
    first = complete_attempt(db, enabled, students[0])
    second = complete_attempt(db, disabled, students[0])
    assert not db.load_familiarization_trials(second)
    before = export_analysis_bundle(db, str(tmp_path / "before"))
    before_summary = csv_rows(before["students"])
    assert len(before_summary) == 2
    assert {r["items_total"] for r in before_summary} == {"6"}
    assert len({r["median_correct_time_ms"] for r in before_summary}) == 1
    disabled_row = next(r for r in before_summary if r["familiarization_enabled"] == "0")
    assert disabled_row["familiarization_status"] == "disabled"
    assert disabled_row["familiarization_1digit_valid_count"] == ""
    assert disabled_row["familiarization_1digit_median_total_response_time_ms"] == ""
    untouched = next(r for r in before_summary if r["familiarization_enabled"] == "1")
    assert untouched["familiarization_status"] == "not_started"

    trials = db.load_familiarization_trials(first)
    for index, trial in enumerate(trials):
        target = trial["target"]
        # Premier essai corrigé, deuxième expiré, troisième faux.
        status = "timeout" if index == 4 else "answered"
        raw = "999" if index == 5 else target
        timing = timing_result(1100 if len(target) == 1 else 1500, raw, corrections=int(index == 3))
        db.save_familiarization_response(trial["id"], raw, timing, status)
    with pytest.raises(RuntimeError, match="déjà été enregistrée"):
        db.save_familiarization_response(trials[0]["id"], "2", timing_result(), "answered")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.exec("UPDATE familiarization_trial SET response_json='{}' WHERE id=?", (trials[0]["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        db.exec("UPDATE familiarization_trial SET target='9' WHERE id=?", (trials[0]["id"],))
    after = export_analysis_bundle(db, str(tmp_path / "after"), assessment_id=enabled)
    summary = csv_rows(after["familiarization_summary"])[0]
    assert summary["familiarization_status"] == "completed"
    assert summary["familiarization_measured_presented"] == "12"
    assert summary["familiarization_1digit_valid_count"] == "4"
    assert summary["familiarization_2digit_valid_count"] == "5"
    assert float(summary["familiarization_1digit_median_total_response_time_ms"]) == 1100
    assert float(summary["familiarization_2digit_median_total_response_time_ms"]) == 1500
    assert len(csv_rows(after["familiarization_trials"])) == 15
    assert len(csv_rows(after["responses"])) == 8
    assert csv_rows(after["students"])[0]["median_correct_time_ms"] == untouched["median_correct_time_ms"]
    path = db.path
    db.close()
    db.open(path)
    assert len(db.load_familiarization_trials(first)) == 15
    assert json.loads(db.load_familiarization_trials(first)[3]["response_json"])["correction_count"] == 1
    db.soft_delete_assessment(enabled, "Test de sélection")
    deleted = export_analysis_bundle(db, str(tmp_path / "deleted"))
    assert csv_rows(deleted["familiarization_trials"]) == []
    assert len(csv_rows(deleted["familiarization_summary"])) == 1


def test_keypad_phase_then_math_and_limits_are_separate(database, qapp):
    db, _, _ = database
    window = pupil_window(database)
    QTest.keyClick(window, Qt.Key_Enter, Qt.KeypadModifier)
    assert window._copy_index == 0
    QTest.keyClick(window.answer, Qt.Key_2)  # Chiffre de la rangée supérieure.
    assert window.answer.text() == ""
    for index, trial in enumerate(window._copy_trials):
        assert window._copy_index == index
        assert window._scored_start_ns is None
        if trial["phase"] == "guided_correction":
            assert window.answer.text() == "58"
            QTest.keyClick(window.answer, Qt.Key_Backspace)
            QTest.keyClick(window.answer, Qt.Key_Enter, Qt.KeypadModifier)
        else:
            enter_number(window.answer, trial["target"])
        if trial["phase"] != "measured":
            window._advance_timer.stop()
            window._advance_after_feedback()
    assert window._copy_done and window.idx == -1
    assert window._scored_start_ns is None
    saved = db.load_familiarization_trials(window.ctx.attempt_id)
    assert all(json.loads(t["response_json"])["is_correct"] for t in saved)
    assert db.q("SELECT COUNT(*) AS n FROM attempt_response")[0]["n"] == 0
    QTest.keyClick(window, Qt.Key_Enter, Qt.KeypadModifier)
    assert window.idx == 0 and window.header.text() == "Essai 1/2"
    window._abort_attempt()
    window._allow_close = True
    window.close()


def test_timeout_and_interruption_during_optional_phase(database, qapp):
    db, _, _ = database
    window = pupil_window(database)
    window._copy_index = 3
    window._render_familiarization()
    window._item_timer.elapsed_ms = lambda: 9000
    window._check_limits()
    assert window._copy_index == 4
    assert window._scored_start_ns is None
    QTest.keyClick(window.answer, Qt.Key_Escape)
    saved = db.load_familiarization_trials(window.ctx.attempt_id)
    assert json.loads(saved[3]["response_json"])["completion_status"] == "timeout"
    assert json.loads(saved[4]["response_json"])["completion_status"] == "interrupted"
    assert saved[5]["response_json"] is None
    assert window._finished_once
    attempt = db.q("SELECT * FROM attempt WHERE id=?", (window.ctx.attempt_id,))[0]
    assert attempt["items_presented"] == 0 and attempt["items_not_presented"] == 6
    window._allow_close = True
    window.close()


def test_disabled_phase_starts_directly_with_calculation(database, qapp):
    window = pupil_window(database, False)
    QTest.keyClick(window, Qt.Key_Enter, Qt.KeypadModifier)
    assert window.idx == 0 and window._copy_index is None
    window._abort_attempt()
    window._allow_close = True
    window.close()


def test_endless_training_keypad_correction_exit_and_no_database(database, qapp):
    db, _, _ = database
    admin = AdminWindow(db)
    assert any(action.text() == "Entraînement" for action in admin.menuBar().actions())
    before = db.q("SELECT COUNT(*) AS n FROM attempt")[0]["n"]
    admin.launch_keyboard_training()
    window = admin._keyboard_training_win
    QTest.keyClick(window.answer, Qt.Key_9)
    assert window.answer.text() == ""
    wrong = "1" if window.target != "1" else "2"
    enter_number(window.answer, wrong)
    assert "Essaie encore" in window.feedback.text()
    QTest.keyClick(window.answer, Qt.Key_Backspace)
    for _ in range(40):
        previous = window.target
        enter_number(window.answer, previous)
        assert window.feedback.text() == "Bien !"
        window._next_timer.stop()
        window._next_number()
        assert window.target != previous
    QTest.keyClick(window.answer, Qt.Key_Escape)
    assert window._closed and admin.isVisible()
    assert db.q("SELECT COUNT(*) AS n FROM attempt")[0]["n"] == before
    assert db.q("SELECT COUNT(*) AS n FROM familiarization_trial")[0]["n"] == 0
    admin.close()
