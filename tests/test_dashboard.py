"""Statistiques, filtres et actualisation du tableau de bord."""
from dataclasses import replace
import time

import pytest
from PySide6.QtCore import Qt, QPoint, QEvent, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QLineEdit, QMessageBox

from app.dashboard_data import build_snapshot, median_center, ranking
from app.ui_dashboard import ResultsDashboard
from app.ui_admin import AdminWindow
from conftest import complete_attempt, create_sample_assessment, timing_result


def test_windows_live_color_scheme(database, qapp):
    if qapp.platformName() != "windows":
        pytest.skip("Requires the native Windows theme provider")
    from app.ui_dashboard import Plot, Series, BLUE
    from app.ui_student import StudentContext, StudentWindow
    from app.ui_keyboard_training import KeyboardTrainingWindow

    previous_style = qapp.style().objectName()
    qapp.setStyle("Fusion")
    hints = qapp.styleHints()
    admin = AdminWindow(database[0])
    pupil = StudentWindow(None, StudentContext(None, None, "Élève test", "Test", [], None, None), lambda: None)
    training = KeyboardTrainingWindow(lambda: None)
    graph = admin.dashboard.plots[0]
    graph.set_model(Plot("Test", message="", series=[Series("Élève", BLUE, [(1, 3, "Test")])]))
    pupil.answer.setText("42")
    pupil._set_practice_color(True)
    try:
        for scheme in (Qt.ColorScheme.Dark, Qt.ColorScheme.Light, Qt.ColorScheme.Dark):
            hints.setColorScheme(scheme)
            qapp.processEvents()
            dark = scheme == Qt.ColorScheme.Dark
            for field in (admin.dashboard.table, admin.dashboard.summary, pupil.answer, training.answer):
                field.ensurePolished()
                bg = field.palette().base().color().lightness()
                fg = field.palette().text().color().lightness()
                assert (bg < 128) == dark and abs(fg - bg) >= 90
            image = graph.grab().toImage()
            assert (image.pixelColor(3, 3).lightness() < 128) == dark
            center = (graph.to_pixel(1, 3) * image.devicePixelRatio()).toPoint()
            assert image.pixelColor(center).name() == BLUE[int(dark)]
            assert (pupil.feedback.palette().windowText().color().lightness() > 128) == dark
            assert pupil.answer.text() == "42"
    finally:
        hints.setColorScheme(Qt.ColorScheme.Unknown)
        qapp.setStyle(previous_style)
        admin.close()
        training.close()
        pupil.deleteLater()


def test_saved_database_follows_current_installation(tmp_path, monkeypatch):
    from app import ui_admin
    root = tmp_path / "current" / "BDD"
    old = tmp_path / "old" / "BDD" / "classe.sqlite"
    old.parent.mkdir(parents=True)
    old.touch()
    root.mkdir(parents=True)
    local = root / old.name
    local.touch()
    pointer = root / "last_db.txt"
    monkeypatch.setattr(ui_admin, "BDD_DIR", str(root))
    monkeypatch.setattr(ui_admin, "LAST_DB_FILE", str(pointer))
    monkeypatch.chdir(tmp_path)
    pointer.write_text(str(old), encoding="utf-8")
    assert ui_admin._load_last_db_path() == str(local)
    assert pointer.read_text(encoding="utf-8") == local.name
    assert ui_admin._load_last_db_path() == str(local)
    local.unlink()
    pointer.write_text(str(old), encoding="utf-8")
    assert ui_admin._load_last_db_path() is None


def test_latest_finished_attempt_excludes_abort_unfinished_and_deleted(database):
    db, project, students = database
    first = create_sample_assessment(db, project, students)
    old = complete_attempt(db, first, students[0])
    latest = complete_attempt(db, first, students[0], 2)
    aborted = db.create_attempt(first, students[0])
    db.finish_attempt(aborted, "teacher_abort", 0)
    db.create_attempt(first, students[1])
    deleted = create_sample_assessment(db, project, students, seed=5)
    complete_attempt(db, deleted, students[2])
    db.soft_delete_assessment(deleted, "Test")
    snap = build_snapshot(db.path, project)
    assert len(snap.results) == 1
    assert snap.results[0].attempt_id == latest != old
    assert snap.excluded == 2
    assert [a["id"] for a in snap.assessments] == [first]
    assert snap.roster[first] == set(students)
    assert snap.results[0].total == 6  # Hors exercices d’entraînement.


def test_missing_times_not_zero_and_time_limit_counts(database):
    db, project, students = database
    assessment = create_sample_assessment(db, project, students)
    attempt = db.create_attempt(assessment, students[0])
    items = [r for r in db.load_attempt_items(attempt) if r["evaluated"]]
    db.save_response(items[0]["attempt_item_id"], 999, False, "999", timing_result(), "answered")
    db.save_response(items[1]["attempt_item_id"], None, None, "", timing_result(text=""), "timeout", "global")
    db.finish_attempt(attempt, "global_time_limit", 2000)
    result = build_snapshot(db.path, project).results[0]
    assert result.accuracy == 0
    assert result.seconds is None
    assert result.mean_correct is None
    assert result.mean_wrong == result.mean_answered == 1
    assert result.timeout == 1 and result.not_presented == 4
    assert ranking([result], "seconds") == []


def test_ranks_ties_and_paired_median_threshold(database):
    db, project, students = database
    assessment = create_sample_assessment(db, project, students)
    complete_attempt(db, assessment, students[0])
    base = build_snapshot(db.path, project).results[0]
    rows = [replace(base, student_id=students[0], correct=4, answered=5, seconds=1),
            replace(base, student_id=students[1], correct=4, answered=5, seconds=3),
            replace(base, student_id=students[2], correct=2, answered=5, seconds=2)]
    assert [rank for rank, _ in ranking(rows, "accuracy")] == [1, 1, 3]
    assert [r.student_id for _, r in ranking(rows, "seconds")] == [students[0], students[2], students[1]]
    assert median_center(rows) == (2, 80)
    assert median_center(rows[:2]) is None
    assert median_center([*rows[:2], replace(rows[2], seconds=None)]) is None


def wait_for_build(widget, qapp):
    deadline = time.monotonic() + 10
    while widget.worker.isRunning() and time.monotonic() < deadline:
        QTest.qWait(10)
    qapp.processEvents()
    assert not widget.worker.isRunning()


def test_reopen_restores_results_without_worker_and_weights_answer_times(database, qapp):
    db, project, students = database
    for seed in (4, 5):
        assessment = create_sample_assessment(db, project, students, seed=seed)
        complete_attempt(db, assessment, students[0], seed)
    built = build_snapshot(db.path, project, use_cache=True)
    path = db.path
    db.close()
    db.open(path)
    dashboard = ResultsDashboard(db)
    dashboard.reload(project)
    assert dashboard.worker is None and dashboard.snapshot == built
    expected = sum(r.mean_answered * r.timed_count for r in built.results) / sum(r.timed_count for r in built.results)
    assert dashboard.table.item(0, 2).text() == f"{expected:.3f}"
    dashboard.close()


def test_build_selection_advanced_crosshair_and_stale_state(database, qapp):
    db, project, students = database
    a = create_sample_assessment(db, project, students, date="2026-01-01")
    b = create_sample_assessment(db, project, students, date="2026-02-01", seed=8)
    for assessment in (a, b):
        for offset, sid in enumerate(students[:3]):
            complete_attempt(db, assessment, sid, offset)
    widget = ResultsDashboard(db)
    widget.resize(1280, 720)
    widget.reload(project)
    widget.show()
    wait_for_build(widget, qapp)
    assert len(widget.snapshot.results) == 6
    assert all(not plot.model.message for plot in widget.plots)
    assert widget.table.rowCount() == 6
    widget.table.selectRow(0)
    assert widget.selected_student == students[0]
    assert widget.plots[0].model.series[1].points
    widget.scope.setCurrentIndex(widget.scope.findData(b))
    assert len(widget.plots[0].model.x_ticks) == 2  # Historique jusqu’à l’évaluation sélectionnée.
    assert all(f"#{b}" in plot.model.note for plot in widget.plots[2:])
    QTest.mouseClick(widget.plots[2], Qt.LeftButton, pos=QPoint(150, 100))
    qapp.processEvents()
    assert widget.advanced == 2 and not widget.sidebar.isVisible()
    assert all(not p.isVisible() for p in (widget.plots[0], widget.plots[1], widget.plots[3]))
    plot = widget.plots[2]
    pixel = plot.to_pixel(1.1, 70)
    x, y = plot.from_pixel(pixel)
    assert x == pytest.approx(1.1) and y == pytest.approx(70)
    messages = []
    widget.status.connect(messages.append)
    def move_to(point):
        qapp.sendEvent(plot, QMouseEvent(QEvent.MouseMove, point, point, Qt.NoButton, Qt.NoButton, Qt.NoModifier))
    move_to(plot.plot_rect().center())
    assert any("Justesse" in message and ":" in message for message in messages)
    px, py, _ = plot.model.series[-1].points[0]
    target = plot.to_pixel(px, py)
    move_to(target + QPointF(2, 2))
    assert plot.hover == target
    QTest.keyClick(widget, Qt.Key_Escape)
    assert widget.advanced is None and widget.sidebar.isVisible()
    snapshot = widget.snapshot
    widget.mark_dirty()
    assert "actualiser" in widget.state.text() and widget.snapshot is snapshot
    widget.close()


def test_zero_one_two_three_participants_and_inflight_invalidation(database, qapp):
    db, project, students = database
    assessment = create_sample_assessment(db, project, students)
    widget = ResultsDashboard(db)
    widget.reload(project, assessment)
    for count in range(4):
        if count:
            complete_attempt(db, assessment, students[count-1], count)
        widget.build()
        wait_for_build(widget, qapp)
        assert bool(widget.plots[2].model.message) == (count < 3)
        assert bool(widget.plots[3].model.message) == (count < 2)
        assert widget.plots[0].model.message  # Une seule évaluation, donc aucune courbe d’évolution.
    widget.build()
    widget.reload(None)
    wait_for_build(widget, qapp)
    assert widget.snapshot is None and not widget.build_button.isEnabled()
    widget.close()


def test_admin_edits_and_removes_selected_student(database, qapp, monkeypatch):
    db, project, students = database
    admin = AdminWindow(db)
    table = admin.dashboard.table
    sid = table.item(0, 0).data(Qt.UserRole)
    def edit(dialog):
        last, first = dialog.findChildren(QLineEdit)
        last.setText("Nom corrigé")
        first.setText("Prénom corrigé")
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", edit)
    table.cellDoubleClicked.emit(0, 0)
    assert db.get_student_identity(sid)["first_name"] == "Prénom corrigé"
    row = next(i for i in range(table.rowCount()) if table.item(i, 0).data(Qt.UserRole) == sid)
    table.selectRow(row)
    for decision in (QMessageBox.No, QMessageBox.Yes):
        monkeypatch.setattr(QMessageBox, "question", lambda *args: decision)
        admin.dashboard.remove_button.click()
        assert (sid in [s["id"] for s in db.list_students(project)]) == (decision == QMessageBox.No)
    assert table.rowCount() == len(students) - 1
    admin.close()


def test_admin_project_scope_and_small_screen(database, qapp):
    db, project, students = database
    assessment = create_sample_assessment(db, project, students)
    other = db.exec("INSERT INTO project(name) VALUES('Autre classe')")
    admin = AdminWindow(db)
    admin.resize(1280, 720)
    admin.show()
    qapp.processEvents()
    admin.dashboard.scope.setCurrentIndex(admin.dashboard.scope.findData(assessment))
    assert admin.assessment_id == assessment
    assert admin.buttons["Lancer la passation"].isEnabled()
    admin.dashboard.projects.setCurrentIndex(admin.dashboard.projects.findData(other))
    assert admin.project_id == other and admin.assessment_id is None
    assert admin.dashboard.table.rowCount() == 0
    assert not admin.buttons["Lancer la passation"].isEnabled()
    assert admin.width() == 1280 and admin.height() == 720
    admin.close()
