"""Génère une classe entièrement fictive pour les essais et les démonstrations."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import random
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assessment_service import create_assessment
from app.config import AssessmentConfig
from app.db import Database
from app.export import export_analysis_bundle
from app.graph import generate_analysis_outputs
from app.timing import KeyTiming, TimingResult


def synthetic_timing(total_ms: float, answer_text: str, corrected: bool, timestamp: datetime) -> TimingResult:
    reaction_ms = round(total_ms * 0.72, 3)
    typing_ms = round(total_ms - reaction_ms, 3)
    events: list[KeyTiming] = []
    if answer_text:
        step = typing_ms / max(1, len(answer_text) + int(corrected))
        elapsed = reaction_ms
        for digit in answer_text:
            events.append(KeyTiming("digit", digit, round(elapsed, 3)))
            elapsed += step
        if corrected:
            events.append(KeyTiming("correction", "backspace", round(min(total_ms - 2, elapsed), 3)))
    events.append(KeyTiming("validate", "", round(total_ms, 3)))
    first_key_at = timestamp + timedelta(milliseconds=reaction_ms) if answer_text else None
    return TimingResult(
        presented_at=timestamp.isoformat(timespec="milliseconds"),
        first_key_at=first_key_at.isoformat(timespec="milliseconds") if first_key_at else None,
        validated_at=(timestamp + timedelta(milliseconds=total_ms)).isoformat(timespec="milliseconds"),
        reaction_time_first_key_ms=reaction_ms if answer_text else None,
        typing_time_ms=typing_ms if answer_text else None,
        total_response_time_ms=round(total_ms, 3),
        keystroke_count=len(answer_text) + int(corrected),
        correction_count=int(corrected),
        key_events=tuple(events),
    )


def generate(output_dir: Path, run_r: bool = True) -> None:
    """Génère deux évaluations pour 25 élèves fictifs et exporte les résultats."""

    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / "synthetic_class.sqlite"
    if database_path.exists():
        database_path.unlink()
    identity_dir = output_dir / "_identities"
    if identity_dir.exists():
        shutil.rmtree(identity_dir)
    for generated_dir in (output_dir / "csv", output_dir / "analysis"):
        if generated_dir.exists():
            shutil.rmtree(generated_dir)

    db = Database(str(database_path), automatic_backups=False)
    project_id = db.exec(
        "INSERT INTO project(name,created_at) VALUES(?,?)",
        ("Classe synthétique de démonstration", "2026-01-01T08:00:00+00:00"),
    )
    student_ids = [
        db.create_student(project_id, f"NOM{index:02d}", f"Élève{index:02d}", "classe")
        for index in range(1, 26)
    ]
    assessment_ids: list[int] = []
    source_id = None
    for session_index, (title, session_date, seed) in enumerate(
        (("Évaluation étalon", "2026-01-15", 111_001), ("Évaluation finale", "2026-05-15", 333_003)), 1
    ):
        config = AssessmentConfig(
            operations=("multiplication",),
            operand_1_values=tuple(range(2, 10)),
            operand_2_values=tuple(range(2, 10)),
            n_scored_items=24,
            n_practice_items=2,
            anchor_count=0 if source_id is None else 6,
            anchor_source_assessment_id=source_id,
            assessment_date=session_date,
            academic_period=f"Période {session_index}",
            group_id="classe",
            random_seed=seed,
            assessment_version=str(session_index),
        )
        assessment_id = create_assessment(
            db, project_id, title, config, student_ids
        )
        assessment_ids.append(assessment_id)
        source_id = assessment_id
        session_clock = datetime.fromisoformat(session_date).replace(hour=8, tzinfo=timezone.utc)
        for pupil_index, student_id in enumerate(student_ids, 1):
            rng = random.Random(seed + pupil_index * 101)
            attempt_id = db.create_attempt(assessment_id, student_id)
            elapsed_ms = 0.0
            for item in db.load_attempt_items(attempt_id):
                skill = 0.57 + 0.014 * pupil_index + 0.10 * (session_index - 1)
                difficulty_penalty = 0.10 if item["difficulty_category"] == "hard" else 0.03 if item["difficulty_category"] == "medium" else 0
                probability_correct = max(0.20, min(0.99, skill - difficulty_penalty))
                base_time = 3800 - 48 * pupil_index - 450 * (session_index - 1)
                if item["difficulty_category"] == "hard":
                    base_time += 850
                total_ms = max(500, rng.lognormvariate(math.log(max(700, base_time)), 0.22))
                presented_at = session_clock + timedelta(minutes=pupil_index * 4, milliseconds=elapsed_ms)
                is_practice = bool(item["is_practice"])
                random_value = rng.random()
                if not is_practice and random_value < 0.015:
                    timing = synthetic_timing(total_ms, "", False, presented_at)
                    db.save_response(item["attempt_item_id"], None, None, "", timing, "omission", "none")
                elif not is_practice and random_value < 0.035:
                    timing = synthetic_timing(6000, "", False, presented_at)
                    db.save_response(item["attempt_item_id"], None, None, "", timing, "timeout", "item")
                else:
                    correct = rng.random() < probability_correct or is_practice
                    expected = int(item["expected"])
                    answer = expected if correct else max(0, expected + rng.choice((-10, -2, -1, 1, 2, 10)))
                    answer_text = str(answer)
                    corrected = rng.random() < 0.08
                    timing = synthetic_timing(total_ms, answer_text, corrected, presented_at)
                    db.save_response(
                        item["attempt_item_id"], answer, correct, answer_text, timing, "answered", "none"
                    )
                elapsed_ms += total_ms + 180
            db.finish_attempt(attempt_id, "completed", elapsed_ms)

    csv_dir = output_dir / "csv"
    export_analysis_bundle(db, str(csv_dir), assessment_id=None, include_nominative_internal=True)
    if run_r:
        generate_analysis_outputs(
            db,
            assessment_ids[-1],
            str(output_dir / "analysis"),
            assessment_ids=assessment_ids,
        )
    db.close()
    (output_dir / "README.md").write_text(
        "# Classe fictive de démonstration\n\n"
        "25 élèves fictifs, une évaluation étalon et une finale, chacune avec 24 calculs notés.\n\n"
        "Les résultats et les identités ont été créés par le script de démonstration.\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère les données d’une classe fictive.")
    parser.add_argument("--output", type=Path, default=ROOT / "examples", help="dossier de destination")
    parser.add_argument("--skip-r", action="store_true", help="génère la base et les CSV sans lancer R")
    args = parser.parse_args()
    generate(args.output.resolve(), run_r=not args.skip_r)


if __name__ == "__main__":
    main()
