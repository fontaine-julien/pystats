"""Migration et sauvegarde des anciens schémas."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from app.db import Database
from app.version import SCHEMA_VERSION
from conftest import complete_attempt, create_sample_assessment, timing_result


def test_reopen_with_historical_started_assessment_lock(database):
    db, project, students = database
    assessment_id = create_sample_assessment(db, project, students)
    complete_attempt(db, assessment_id, students[0])
    path = db.path
    frozen = db.q("SELECT frozen_at,items_hash FROM assessment WHERE id=?", (assessment_id,))[0]
    responses = db.q("SELECT * FROM attempt_response ORDER BY id")
    db.exec("DROP TRIGGER prevent_started_assessment_thaw")
    db.exec("""
        CREATE TRIGGER prevent_started_assessment_thaw BEFORE UPDATE OF frozen_at ON assessment
        WHEN EXISTS (SELECT 1 FROM attempt WHERE assessment_id=OLD.id)
        BEGIN SELECT RAISE(ABORT, 'started assessment is locked'); END
    """)
    for _ in range(2):
        db.close()
        db.open(path)
        assert db.q("SELECT frozen_at,items_hash FROM assessment WHERE id=?", (assessment_id,))[0] == frozen
        assert db.verify_assessment_integrity(assessment_id)
        assert db.q("SELECT * FROM attempt_response ORDER BY id") == responses
        with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
            conn.execute("UPDATE assessment SET frozen_at=NULL WHERE id=?", (assessment_id,))


def test_failed_backfill_restores_existing_protections(database):
    db, project, students = database
    assessment_id = create_sample_assessment(db, project, students)
    complete_attempt(db, assessment_id, students[0])
    before = db.q("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")
    db.exec("""CREATE TRIGGER fail_backfill BEFORE UPDATE OF position ON assessment_item
               BEGIN SELECT RAISE(ABORT, 'simulated migration failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="simulated migration failure"):
        db._migrate()
    db.exec("DROP TRIGGER fail_backfill")
    assert db.q("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name") == before
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute("UPDATE attempt_response SET answer=NULL")


def test_legacy_names_move_to_sidecar_and_timeout_remains_distinct(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE project(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE student(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, last_name TEXT NOT NULL, first_name TEXT NOT NULL);
        CREATE TABLE assessment(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, type TEXT NOT NULL);
        CREATE TABLE assessment_item(id INTEGER PRIMARY KEY, assessment_id INTEGER NOT NULL, idx INTEGER NOT NULL, a INTEGER NOT NULL, expected INTEGER NOT NULL, evaluated INTEGER NOT NULL);
        CREATE TABLE assessment_roster(assessment_id INTEGER, student_id INTEGER);
        CREATE TABLE attempt(id INTEGER PRIMARY KEY, assessment_id INTEGER NOT NULL, student_id INTEGER NOT NULL);
        CREATE TABLE attempt_item(id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL, idx INTEGER NOT NULL, a INTEGER NOT NULL, expected INTEGER NOT NULL, evaluated INTEGER NOT NULL);
        CREATE TABLE attempt_response(id INTEGER PRIMARY KEY, attempt_item_id INTEGER NOT NULL, answer INTEGER NOT NULL, correct INTEGER NOT NULL);
        INSERT INTO project VALUES(1,'Legacy');
        INSERT INTO student VALUES(1,1,'DUPONT','Alice');
        INSERT INTO assessment VALUES(1,1,'complements_100');
        INSERT INTO assessment_item VALUES(1,1,0,40,60,1);
        INSERT INTO assessment_roster VALUES(1,1);
        INSERT INTO attempt VALUES(1,1,1);
        INSERT INTO attempt_item VALUES(1,1,0,40,60,1);
        """
    )
    connection.commit()
    connection.close()
    db = Database(str(path), automatic_backups=False)
    assert db.q("SELECT last_name,first_name FROM student WHERE id=1")[0]["last_name"] == ""
    assert db.get_student_identity(1)["last_name"] == "DUPONT"
    response_id = db.save_response(1, None, None, "", timing_result(text=""), "timeout", "item")
    row = db.q("SELECT answer,correct,completion_status FROM attempt_response WHERE id=?", (response_id,))[0]
    assert row["completion_status"] == "timeout"
    assert list((tmp_path / "backups").glob(f"legacy_before_v{SCHEMA_VERSION}_*.sqlite"))
    db.delete_student_assessment(1, 1)
    assert not db.q("SELECT * FROM attempt_response")
    assert not db.q("SELECT * FROM attempt_item")
    assert not db.q("SELECT * FROM attempt")
    assert db.q("SELECT * FROM assessment_roster")
    assert db.get_student_identity(1) is not None
    db.remove_student(1)
    assert not db.q("SELECT * FROM assessment_roster")
    assert not db.q("SELECT * FROM identity.student_identity")
    assert not db.q("SELECT * FROM student")
    db.close()
