"""Production des rapports R et traitement des entrées incomplètes."""

from __future__ import annotations

from pathlib import Path
import csv
import math
import os
import shutil
import statistics
import struct
import subprocess

import pytest

from app.assessment_service import create_assessment
from app.config import AssessmentConfig
from app.export import export_analysis_bundle
from scripts.generate_synthetic_example import generate
from conftest import complete_attempt, timing_result


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def synthetic_csv_dir(tmp_path_factory):
    destination = tmp_path_factory.mktemp("classe_fictive")
    generate(destination, run_r=False)
    return destination / "csv"


def test_r_accepts_mixed_familiarization_and_missing_optional_files(database, tmp_path):
    db, project, students = database
    assessments = []
    for enabled, date in ((False, "2026-01-01"), (True, "2026-03-01")):
        assessment = create_assessment(db, project, "Test mixte", AssessmentConfig(
            n_scored_items=6, assessment_date=date, familiarization_enabled=enabled,
        ), students)
        assessments.append(assessment)
        for index, student in enumerate(students):
            attempt = complete_attempt(db, assessment, student, index)
            if enabled and index == 0:
                # Mélange de phases absentes et incomplètes.
                trial = db.load_familiarization_trials(attempt)[3]
                db.save_familiarization_response(trial["id"], trial["target"], timing_result(text=trial["target"]), "answered")
    destination = tmp_path / "mixed"
    exports = export_analysis_bundle(db, str(destination))
    for key in ("familiarization_trials", "familiarization_summary"):
        Path(exports[key]).unlink()
    identifiers = [db.q("SELECT assessment_uuid FROM assessment WHERE id=?", (a,))[0]["assessment_uuid"] for a in assessments]
    output = tmp_path / "mixed_results"
    process = subprocess.run(
        ["Rscript", str(ROOT / "analysis" / "run_all.R"), str(destination), str(output), identifiers[1], identifiers[0]],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        env={**os.environ, "PYSTATS_BOOTSTRAP_REPLICATES": "100"},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert (output / "final_performance_scatter.png").exists()
    with (output / "final_performance_scatter_data.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(students)


def test_r_generates_all_static_formats_and_reports(tmp_path: Path, synthetic_csv_dir: Path) -> None:
    input_dir = synthetic_csv_dir
    output_dir = tmp_path / "r_outputs"
    with (input_dir / "student_assessment_summary.csv").open(encoding="utf-8", newline="") as stream:
        assessment_pairs = sorted({(row["assessment_date"], row["assessment_id"]) for row in csv.DictReader(stream)})
    baseline_id = assessment_pairs[0][1]
    focus_id = assessment_pairs[-1][1]
    log_path = tmp_path / "r_success.log"
    with log_path.open("w+", encoding="utf-8") as log_stream:
        process = subprocess.run(
            [
                "Rscript", str(ROOT / "analysis" / "run_all.R"), str(input_dir), str(output_dir),
                focus_id, baseline_id,
            ],
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "PYSTATS_BOOTSTRAP_REPLICATES": "100"},
        )
        log_stream.seek(0)
        execution_output = log_stream.read()
    assert process.returncode == 0, execution_output
    for extension in ("png", "pdf", "svg"):
        assert len(list((output_dir / "figures").glob(f"*.{extension}"))) == (14 if extension == "pdf" else 12)
    for name in ("08_correlogram_par_evaluation", "13_distribution_temps"):
        assert (output_dir / "figures" / f"{name}.pdf").stat().st_size > 1000
    assert (output_dir / "class_report.pdf").stat().st_size > 1000
    assert (output_dir / "parallel_coordinates_interactive.html").stat().st_size > 1000
    assert (output_dir / "correlation_results.csv").stat().st_size > 100
    assert (output_dir / "final_performance_scatter.png").stat().st_size > 10_000
    assert (output_dir / "final_performance_scatter.pdf").stat().st_size > 5_000
    assert (output_dir / "final_performance_scatter.html").stat().st_size > 5_000
    assert not (output_dir / "final_performance_scatter.svg").exists()
    with (output_dir / "final_performance_scatter.png").open("rb") as stream:
        header = stream.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", header[16:24])
    assert (width, height) == (3000, 2100)

    with (output_dir / "final_performance_scatter_data.csv").open(encoding="utf-8", newline="") as stream:
        final_rows = list(csv.DictReader(stream))
    assert len(final_rows) == 25
    assert len({row["student_export_id"] for row in final_rows}) == 25
    assert all("NOM" not in str(value) and "Élève" not in str(value) for row in final_rows for value in row.values())
    eligible = [row for row in final_rows if row["plot_eligible"] == "TRUE"]
    assert eligible
    assert all(row["baseline_assessment_id"] == baseline_id for row in eligible)
    assert all(row["final_assessment_id"] == focus_id for row in eligible)
    assert all(
        math.isclose(
            float(row["accuracy_change_proportion"]),
            float(row["final_accuracy"]) - float(row["baseline_accuracy"]),
            abs_tol=1e-12,
        )
        for row in eligible
    )
    sample = eligible[0]
    with (input_dir / "responses_long_pseudonymized.csv").open(encoding="utf-8", newline="") as stream:
        raw_rows = [
            row for row in csv.DictReader(stream)
            if row["student_export_id"] == sample["student_export_id"]
            and row["assessment_id"] == focus_id
            and row["is_practice_item"] == "0"
        ]
    valid_presented = [
        row for row in raw_rows
        if row["completion_status"] in {"answered", "omission", "timeout", "global_timeout"}
    ]
    valid_answered = [row for row in raw_rows if row["completion_status"] == "answered"]
    expected_correct = sum(row["is_correct"] == "1" for row in valid_answered)
    expected_duration = sum(float(row["total_response_time_ms"]) for row in valid_answered) / 1000
    assert int(sample["final_items_presented"]) == len(valid_presented)
    assert int(sample["final_correct_count"]) == expected_correct
    assert math.isclose(float(sample["final_exact_rate_per_second"]), expected_correct / expected_duration, rel_tol=1e-10)
    assert float(eligible[0]["principal_direction_x"]) + float(eligible[0]["principal_direction_y"]) >= 0
    if eligible[0]["center_method"] == "median_center_classical_covariance_fallback":
        assert math.isclose(
            float(eligible[0]["robust_center_x"]),
            statistics.median(float(row["final_x_value"]) for row in eligible),
            abs_tol=1e-12,
        )
    with (output_dir / "graph_generation_status.csv").open(encoding="utf-8", newline="") as stream:
        statuses = list(csv.DictReader(stream))
    final_status = next(row for row in statuses if row["file_stem"] == "final_performance_scatter")
    assert final_status["status"] == "generated"
    assert "Ellipse omise pour le groupe" in (output_dir / "r_analysis.log").read_text(encoding="utf-8")


def test_r_reports_insufficient_longitudinal_data_without_failure(tmp_path: Path, synthetic_csv_dir: Path) -> None:
    input_dir = synthetic_csv_dir
    with (input_dir / "student_assessment_summary.csv").open(encoding="utf-8", newline="") as stream:
        first_id = sorted({(row["assessment_date"], row["assessment_id"]) for row in csv.DictReader(stream)})[0][1]
    output_dir = tmp_path / "single_session_output"
    log_path = tmp_path / "single_session.log"
    with log_path.open("w+", encoding="utf-8") as log_stream:
        process = subprocess.run(
            ["Rscript", str(ROOT / "analysis" / "run_all.R"), str(input_dir), str(output_dir), first_id, first_id],
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "PYSTATS_BOOTSTRAP_REPLICATES": "100"},
        )
    assert process.returncode == 0
    with (output_dir / "graph_generation_status.csv").open(encoding="utf-8", newline="") as stream:
        statuses = list(csv.DictReader(stream))
    final_status = next(row for row in statuses if row["file_stem"] == "final_performance_scatter")
    assert final_status["status"] == "not_generated"
    assert final_status["reason"] == "manque de données"
    assert "deux évaluations distinctes" in final_status["comment"]
    assert not (output_dir / "final_performance_scatter.png").exists()


def test_r_fails_clearly_on_incomplete_files(tmp_path: Path, synthetic_csv_dir: Path) -> None:
    input_dir = tmp_path / "incomplete"
    input_dir.mkdir()
    source = synthetic_csv_dir / "responses_long_pseudonymized.csv"
    shutil.copy2(source, input_dir / source.name)
    log_path = tmp_path / "r_failure.log"
    with log_path.open("w+", encoding="utf-8") as log_stream:
        process = subprocess.run(
            ["Rscript", str(ROOT / "analysis" / "run_all.R"), str(input_dir), str(tmp_path / "out")],
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        log_stream.seek(0)
        execution_output = log_stream.read()
    assert process.returncode != 0
    assert "Fichier obligatoire introuvable" in execution_output
