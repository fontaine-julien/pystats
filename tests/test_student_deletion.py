"""Suppression ciblée des élèves et des passations."""

import csv
import sqlite3
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu, QMessageBox

from app.assessment_service import create_assessment
from app.config import AssessmentConfig
from app.dashboard_data import build_snapshot
from app.export import export_analysis_bundle
from app.ui_admin import AdminWindow
from conftest import complete_attempt, create_sample_assessment, timing_result


TABLES = (
    "student", "identity.student_identity", "assessment_roster", "attempt",
    "attempt_item", "attempt_response", "response_key_event",
    "familiarization_trial", "audit_event", "dashboard_cache",
)


@pytest.mark.parametrize("full_removal", [False, True])
def test_delete_all_target_attempts_and_rebuild(database, tmp_path, full_removal):
    db, project, pupils = database
    pretest = create_sample_assessment(db, project, pupils)
    final = create_assessment(db, project, "T1", AssessmentConfig(
        n_scored_items=6, familiarization_enabled=True, assessment_date="2026-03-01",
    ), pupils)
    for pupil in pupils[:2]:
        complete_attempt(db, pretest, pupil)
        complete_attempt(db, final, pupil)
    complete_attempt(db, final, pupils[0])
    unfinished = db.create_attempt(final, pupils[0])
    trial = db.load_familiarization_trials(unfinished)[0]
    db.save_familiarization_response(trial["id"], trial["target"],
                                    timing_result(text=trial["target"]), "answered")
    build_snapshot(db.path, project, use_cache=True)
    other_before = db.q("SELECT * FROM attempt WHERE student_id=?", (pupils[1],))
    pretest_before = db.q("SELECT * FROM attempt WHERE student_id=? AND assessment_id=?", (pupils[0], pretest))
    protected = db.q("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")
    export_id = db.get_student_identity(pupils[0])["export_id"]
    if full_removal:
        db.remove_student(pupils[0])
        assert db.get_student_identity(pupils[0]) is None
        assert not db.q("SELECT * FROM assessment_roster WHERE student_id=?", (pupils[0],))
        assert not db.q("SELECT * FROM attempt WHERE student_id=?", (pupils[0],))
    else:
        db.delete_student_assessment(pupils[0], final)
        assert db.get_student_identity(pupils[0]) is not None
        assert db.q("SELECT * FROM attempt WHERE student_id=? AND assessment_id=?",
                    (pupils[0], pretest)) == pretest_before
        assert db.q("SELECT * FROM assessment_roster WHERE student_id=? AND assessment_id=?", (pupils[0], final))
    assert not db.q("SELECT * FROM attempt WHERE student_id=? AND assessment_id=?", (pupils[0], final))
    assert not db.q("SELECT * FROM dashboard_cache")
    assert db.q("SELECT * FROM attempt WHERE student_id=?", (pupils[1],)) == other_before
    assert db.q("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name") == protected
    assert not db.q("PRAGMA foreign_key_check")
    assert not db.q("SELECT * FROM audit_event WHERE entity_type='attempt' "
                    "AND CAST(entity_id AS INTEGER) NOT IN (SELECT id FROM attempt)")
    assert not db.q("SELECT * FROM audit_event WHERE event_type LIKE '%deleted%' OR event_type='student_removed'")
    snap = build_snapshot(db.path, project, use_cache=True)
    assert len(snap.results) == (2 if full_removal else 3)
    outputs = export_analysis_bundle(db, str(tmp_path / "exports"))
    with open(outputs["responses"], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    final_uuid = db.q("SELECT assessment_uuid FROM assessment WHERE id=?", (final,))[0][0]
    assert not any(r["student_export_id"] == export_id and
                   (full_removal or r["assessment_id"] == final_uuid) for r in rows)
    if not full_removal:
        complete_attempt(db, final, pupils[0])
        assert len(build_snapshot(db.path, project, use_cache=True).results) == 4
    db_path = db.path
    db.close()
    db.open(db_path)
    assert not db.q("PRAGMA foreign_key_check")


def test_delete_failure_restores_data_and_guards(database):
    db, project, pupils = database
    assessment = create_assessment(db, project, "Test", AssessmentConfig(
        n_scored_items=6, familiarization_enabled=True,
    ), pupils)
    complete_attempt(db, assessment, pupils[0])
    build_snapshot(db.path, project, use_cache=True)
    before = {table: db.q(f"SELECT * FROM {table}") for table in TABLES}
    triggers = db.q("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")
    db.exec("CREATE TRIGGER fail_pupil_deletion BEFORE DELETE ON student "
            "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="simulated failure"):
        db.remove_student(pupils[0])
    db.exec("DROP TRIGGER fail_pupil_deletion")
    assert {table: db.q(f"SELECT * FROM {table}") for table in TABLES} == before
    assert db.q("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name") == triggers
    with pytest.raises(sqlite3.IntegrityError, match="immutable"), db.transaction() as conn:
        conn.execute("DELETE FROM attempt_response")


def test_context_menu_cancels_then_clears_only_selected_pupil(database, qapp, monkeypatch):
    db, project, pupils = database
    assessment = create_sample_assessment(db, project, pupils)
    for pupil in pupils[:2]:
        complete_attempt(db, assessment, pupil)
    build_snapshot(db.path, project, use_cache=True)
    db.set_meta("last_assessment_id", str(assessment))
    admin = AdminWindow(db)
    admin.show()
    qapp.processEvents()
    dashboard = admin.dashboard
    table = dashboard.table
    position = table.visualItemRect(table.item(0, 0)).center()
    class SelectFirstMenu(QMenu):
        def exec(self, position):
            return self.actions()[0]
    monkeypatch.setattr("app.ui_dashboard.QMenu", SelectFirstMenu)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(args[2]))
    prompts = []
    def answer(*args):
        prompts.append(args)
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, "question", answer)
    table.selectRow(1)
    table.customContextMenuRequested.emit(position)
    assert dashboard.selected_student == pupils[0]
    assert db.q("SELECT 1 FROM attempt WHERE student_id=?", (pupils[0],))
    assert "NOM1" in prompts[-1][2] and "Test" in prompts[-1][2]
    assert prompts[-1][-1] == QMessageBox.No
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    table.customContextMenuRequested.emit(position)
    if dashboard.worker:
        deadline = time.monotonic() + 10
        while dashboard.worker.isRunning() and time.monotonic() < deadline:
            QTest.qWait(10)
        qapp.processEvents()
        assert not dashboard.worker.isRunning()
    assert not db.q("SELECT 1 FROM attempt WHERE student_id=?", (pupils[0],))
    assert len(db.list_students(project)) == 6
    assert len(dashboard.snapshot.results) == 1
    assert table.item(0, 1).text() == "—"
    enabled = []
    monkeypatch.setattr(SelectFirstMenu, "exec", lambda menu, position: enabled.append(menu.actions()[0].isEnabled()))
    table.customContextMenuRequested.emit(position)
    dashboard.scope.setCurrentIndex(0)
    table.customContextMenuRequested.emit(position)
    assert enabled == [False, False]
    admin.close()
