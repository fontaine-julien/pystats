"""Jeux de données fictifs partagés par les tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assessment_service import create_assessment
from app.config import AssessmentConfig
from app.db import Database
from app.timing import KeyTiming, TimingResult


@pytest.fixture(scope="session")
def qapp():
    """Réutilise la même application Qt pendant toute la session."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    app = QApplication.instance() or QApplication([])
    if os.name == "nt":
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/verdana.ttf")
    yield app


def timing_result(total_ms: float = 1000.0, text: str = "12", corrections: int = 0) -> TimingResult:
    presented = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    reaction = 600.0 if text else None
    events = [KeyTiming("digit", digit, 600.0 + index * 100) for index, digit in enumerate(text)]
    events.extend(KeyTiming("correction", "backspace", 850.0 + index) for index in range(corrections))
    events.append(KeyTiming("validate", "", total_ms))
    return TimingResult(
        presented_at=presented.isoformat(timespec="milliseconds"),
        first_key_at=presented.isoformat(timespec="milliseconds") if text else None,
        validated_at=presented.isoformat(timespec="milliseconds"),
        reaction_time_first_key_ms=reaction,
        typing_time_ms=total_ms - reaction if reaction is not None else None,
        total_response_time_ms=total_ms,
        keystroke_count=len(text) + corrections,
        correction_count=corrections,
        key_events=tuple(events),
    )


@pytest.fixture
def database(tmp_path: Path):
    db = Database(str(tmp_path / "test.sqlite"), automatic_backups=False)
    project_id = db.exec(
        "INSERT INTO project(name,created_at) VALUES(?,?)", ("Classe test", "2026-01-01T08:00:00+00:00")
    )
    student_ids = [db.create_student(project_id, f"NOM{index}", f"Prenom{index}") for index in range(1, 7)]
    yield db, project_id, student_ids
    db.close()


def create_sample_assessment(
    db: Database,
    project_id: int,
    student_ids: list[int],
    seed: int = 1234,
    date: str = "2026-01-15",
    source_id: int | None = None,
) -> int:
    config = AssessmentConfig(
        operations=("multiplication",),
        operand_1_values=(2, 3, 4),
        operand_2_values=(2, 3, 4),
        n_scored_items=6,
        anchor_count=2 if source_id else 0,
        anchor_source_assessment_id=source_id,
        assessment_date=date,
        academic_period="P1",
        random_seed=seed,
    )
    return create_assessment(db, project_id, "Test", config, student_ids)


def complete_attempt(db: Database, assessment_id: int, student_id: int, pupil_offset: int = 0) -> int:
    attempt_id = db.create_attempt(assessment_id, student_id)
    scored_index = 0
    total = 0.0
    for item in db.load_attempt_items(attempt_id):
        is_practice = bool(item["is_practice"])
        if is_practice:
            answer = int(item["expected"])
            db.save_response(
                item["attempt_item_id"], answer, True, str(answer), timing_result(700, str(answer)), "answered"
            )
            continue
        scored_index += 1
        duration = 900.0 + 100 * scored_index + 10 * pupil_offset
        total += duration
        if scored_index == 2 and pupil_offset == 0:
            db.save_response(
                item["attempt_item_id"], None, None, "", timing_result(duration, ""), "omission"
            )
        elif scored_index == 3 and pupil_offset == 1:
            db.save_response(
                item["attempt_item_id"], None, None, "", timing_result(duration, ""), "timeout", "item"
            )
        else:
            correct = (scored_index + pupil_offset) % 4 != 0
            expected = int(item["expected"])
            answer = expected if correct else expected + 1
            db.save_response(
                item["attempt_item_id"], answer, correct, str(answer), timing_result(duration, str(answer)), "answered"
            )
    db.finish_attempt(attempt_id, "completed", total)
    return attempt_id
