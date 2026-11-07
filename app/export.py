"""Exports CSV pseudonymisés, nominatifs et agrégés."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Sequence

from app.db import Database
from app.schema import ELIGIBLE_ATTEMPT_SQL
from app.familiarization_export import (
    MEASURE_COLUMNS, SUMMARY_COLUMNS as FAMILIARIZATION_SUMMARY_COLUMNS,
    TRIAL_COLUMNS as FAMILIARIZATION_TRIAL_COLUMNS, familiarization_rows,
)


TEACHER_DIR = "Enseignant"
DESCRIPTIVE_DIR = "Donnees_descriptives"
PUBLIC_DIR = "Publication"

RESPONSE_COLUMNS = [
    "assessment_id",
    "assessment_version",
    "assessment_date",
    "academic_period",
    "student_internal_id",
    "student_export_id",
    "group_id",
    "item_id",
    "item_position",
    "is_practice_item",
    "is_anchor_item",
    "operation_type",
    "operand_1",
    "operand_2",
    "expected_answer",
    "entered_answer",
    "is_correct",
    "reaction_time_first_key_ms",
    "typing_time_ms",
    "total_response_time_ms",
    "keystroke_count",
    "correction_count",
    "timeout_status",
    "completion_status",
    "random_seed",
    "software_version",
    "attempt_id",
    "attempt_duration_ms",
    "fact_family",
    "difficulty_category",
]


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], columns: Sequence[str]) -> str:
    """Écrit le CSV en UTF-8 dans un ordre de colonnes stable."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in columns})
    return str(path)


def _quantile(values: Sequence[float], probability: float) -> float | None:
    """Calcule un quantile empirique par interpolation linéaire."""

    clean = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    return clean[lower] + (clean[upper] - clean[lower]) * (position - lower)


def _mean(values: Sequence[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.fmean(clean) if clean else None


def _median(values: Sequence[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(clean) if clean else None


def _stdev(values: Sequence[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.stdev(clean) if len(clean) > 1 else None


def _round_or_none(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


def response_rows(
    db: Database,
    assessment_id: int | None = None,
    assessment_ids: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    """Produit une ligne par item de passation, y compris les items non présentés."""

    conditions = ["a.deleted_at IS NULL", "s.deleted_at IS NULL", ELIGIBLE_ATTEMPT_SQL]
    params: list[Any] = []
    if assessment_id is not None and assessment_ids is not None:
        raise ValueError("Indiquez un seul des deux paramètres assessment_id et assessment_ids.")
    if assessment_id is not None:
        conditions.append("a.id=?")
        params.append(assessment_id)
    elif assessment_ids is not None:
        selected = [int(value) for value in assessment_ids]
        if not selected:
            return []
        conditions.append(f"a.id IN ({','.join('?' for _ in selected)})")
        params.extend(selected)
    rows = db.q(
        "SELECT a.assessment_uuid,a.assessment_version,a.assessment_date,a.academic_period,a.group_id AS assessment_group,"
        "a.random_seed,a.software_version AS assessment_software,att.attempt_uuid,att.duration_ms,att.student_id,s.export_id,s.group_id,"
        "ai.item_uuid,ai.position,ai.is_practice,ai.is_anchor,ai.op,ai.a,ai.b,ai.expected,ai.evaluated,"
        "ai.fact_family,ai.difficulty_category,ar.answer,ar.correct,ar.reaction_time_first_key_ms,ar.typing_time_ms,"
        "ar.total_response_time_ms,ar.keystroke_count,ar.correction_count,ar.timeout_status,ar.completion_status,"
        "ar.software_version AS response_software "
        "FROM attempt att JOIN assessment a ON a.id=att.assessment_id JOIN student s ON s.id=att.student_id "
        "JOIN attempt_item ai ON ai.attempt_id=att.id LEFT JOIN attempt_response ar ON ar.attempt_item_id=ai.id "
        f"WHERE {' AND '.join(conditions)} ORDER BY a.assessment_date,a.id,att.id,ai.position",
        tuple(params),
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        completion = str(row["completion_status"] or "not_presented")
        is_correct: int | None = None
        if completion == "answered":
            is_correct = int(row["correct"] or 0)
        output.append(
            {
                "assessment_id": row["assessment_uuid"],
                "assessment_version": row["assessment_version"],
                "assessment_date": row["assessment_date"],
                "academic_period": row["academic_period"],
                "student_internal_id": row["export_id"],
                "student_export_id": row["export_id"],
                "group_id": row["group_id"] or row["assessment_group"],
                "item_id": row["item_uuid"],
                "item_position": int(row["position"]),
                "is_practice_item": int(row["is_practice"] or 0),
                "is_anchor_item": int(row["is_anchor"] or 0),
                "operation_type": row["op"],
                "operand_1": int(row["a"]),
                "operand_2": int(row["b"] or 0),
                "expected_answer": int(row["expected"]),
                "entered_answer": row["answer"] if completion == "answered" else None,
                "is_correct": is_correct,
                "reaction_time_first_key_ms": row["reaction_time_first_key_ms"],
                "typing_time_ms": row["typing_time_ms"],
                "total_response_time_ms": row["total_response_time_ms"],
                "keystroke_count": int(row["keystroke_count"] or 0),
                "correction_count": int(row["correction_count"] or 0),
                "timeout_status": row["timeout_status"] or "none",
                "completion_status": completion,
                "random_seed": row["random_seed"],
                "software_version": row["response_software"] or row["assessment_software"],
                "attempt_id": row["attempt_uuid"],
                "attempt_duration_ms": row["duration_ms"],
                "fact_family": row["fact_family"],
                "difficulty_category": row["difficulty_category"],
            }
        )
    return output


def _latest_attempt_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retient la dernière passation par élève et par évaluation."""

    latest: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (str(row["assessment_id"]), str(row["student_export_id"]))
        latest[key] = str(row["attempt_id"])
    return [
        row
        for row in rows
        if str(row["attempt_id"]) == latest[(str(row["assessment_id"]), str(row["student_export_id"]))]
    ]


def _student_summaries(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _latest_attempt_rows(rows):
        if not int(row["is_practice_item"]):
            grouped[(str(row["assessment_id"]), str(row["student_export_id"]), str(row["attempt_id"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (assessment_id, student_id, attempt_id), group in grouped.items():
        presented = [row for row in group if row["completion_status"] != "not_presented"]
        answered = [row for row in group if row["completion_status"] == "answered"]
        correct = [row for row in answered if row["is_correct"] == 1]
        timed = [(row["is_correct"], float(row["total_response_time_ms"])) for row in answered
                 if row["total_response_time_ms"] is not None and math.isfinite(row["total_response_time_ms"])
                 and row["total_response_time_ms"] > 0]
        correct_times = [t for outcome, t in timed if outcome == 1]
        wrong_times = [t for outcome, t in timed if outcome == 0]
        all_times = [t for _, t in timed]
        attempt_duration = group[0].get("attempt_duration_ms")
        elapsed_minutes = (
            float(attempt_duration) / 60_000
            if attempt_duration is not None and float(attempt_duration) > 0
            else sum(all_times) / 60_000 if all_times else 0.0
        )
        mean_time = _mean(correct_times)
        sd_time = _stdev(correct_times)
        summaries.append(
            {
                "assessment_id": assessment_id,
                "assessment_date": group[0]["assessment_date"],
                "academic_period": group[0]["academic_period"],
                "student_export_id": student_id,
                "group_id": group[0]["group_id"],
                "attempt_id": attempt_id,
                "items_total": len(group),
                "items_presented": len(presented),
                "items_answered": len(answered),
                "items_correct": len(correct),
                "items_incorrect": len(answered) - len(correct),
                "items_not_presented": len(group) - len(presented),
                "success_rate": round(len(correct) / len(answered), 6) if answered else None,
                "mean_correct_time_ms": _round_or_none(mean_time),
                "mean_incorrect_time_ms": _round_or_none(_mean(wrong_times)),
                "mean_answered_time_ms": _round_or_none(_mean(all_times)),
                "median_correct_time_ms": _round_or_none(_median(correct_times)),
                "correct_time_sd_ms": _round_or_none(sd_time),
                "correct_time_iqr_ms": _round_or_none(
                    None if not correct_times else float(_quantile(correct_times, 0.75)) - float(_quantile(correct_times, 0.25))
                ),
                "correct_time_q10_ms": _round_or_none(_quantile(correct_times, 0.10)),
                "correct_time_q90_ms": _round_or_none(_quantile(correct_times, 0.90)),
                "correct_per_minute": round(len(correct) / elapsed_minutes, 3) if elapsed_minutes > 0 else None,
                "omission_rate": round(sum(row["completion_status"] == "omission" for row in presented) / len(group), 6),
                "timeout_rate": round(sum(row["timeout_status"] != "none" for row in presented) / len(group), 6),
                "time_coefficient_variation": round(sd_time / mean_time, 6) if mean_time and sd_time is not None else None,
                "change_success_rate": None,
                "change_median_correct_time_ms": None,
            }
        )
    by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        by_student[str(summary["student_export_id"])].append(summary)
    for student_rows in by_student.values():
        student_rows.sort(key=lambda row: (str(row["assessment_date"]), str(row["assessment_id"])))
        previous: dict[str, Any] | None = None
        for current in student_rows:
            if previous is not None:
                if current["success_rate"] is not None and previous["success_rate"] is not None:
                    current["change_success_rate"] = round(current["success_rate"] - previous["success_rate"], 6)
                if current["median_correct_time_ms"] is not None and previous["median_correct_time_ms"] is not None:
                    current["change_median_correct_time_ms"] = round(
                        current["median_correct_time_ms"] - previous["median_correct_time_ms"], 3
                    )
            previous = current
    return sorted(summaries, key=lambda row: (str(row["assessment_date"]), str(row["student_export_id"])))


STUDENT_SUMMARY_COLUMNS = [
    "assessment_id", "assessment_date", "academic_period", "student_export_id", "group_id", "attempt_id",
    "items_total", "items_presented", "items_answered", "items_correct", "items_incorrect", "items_not_presented",
    "success_rate", "mean_correct_time_ms", "mean_incorrect_time_ms", "mean_answered_time_ms",
    "median_correct_time_ms", "correct_time_sd_ms", "correct_time_iqr_ms",
    "correct_time_q10_ms", "correct_time_q90_ms", "correct_per_minute", "omission_rate", "timeout_rate",
    "time_coefficient_variation", "change_success_rate", "change_median_correct_time_ms",
    *MEASURE_COLUMNS,
]


def _fact_family_summaries(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _latest_attempt_rows(rows):
        if not int(row["is_practice_item"]):
            grouped[(str(row["assessment_id"]), str(row["fact_family"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (assessment_id, family), group in grouped.items():
        answered = [row for row in group if row["completion_status"] == "answered"]
        correct = [row for row in answered if row["is_correct"] == 1]
        correct_times = [float(row["total_response_time_ms"]) for row in correct if row["total_response_time_ms"] is not None]
        pupil_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in group:
            pupil_rows[str(row["student_export_id"])].append(row)
        difficulty_count = 0
        for pupil_group in pupil_rows.values():
            pupil_answered = [row for row in pupil_group if row["completion_status"] == "answered"]
            rate = sum(row["is_correct"] == 1 for row in pupil_answered) / len(pupil_answered) if pupil_answered else 0.0
            if rate < 0.8:
                difficulty_count += 1
        elapsed_minutes = sum(float(row["total_response_time_ms"] or 0) for row in answered) / 60_000
        summaries.append(
            {
                "assessment_id": assessment_id,
                "assessment_date": group[0]["assessment_date"],
                "academic_period": group[0]["academic_period"],
                "fact_family": family,
                "student_count": len(pupil_rows),
                "item_response_count": len(group),
                "answered_count": len(answered),
                "success_rate": round(len(correct) / len(answered), 6) if answered else None,
                "mean_correct_time_ms": _round_or_none(_mean(correct_times)),
                "median_correct_time_ms": _round_or_none(_median(correct_times)),
                "correct_time_iqr_ms": _round_or_none(
                    None if not correct_times else float(_quantile(correct_times, 0.75)) - float(_quantile(correct_times, 0.25))
                ),
                "correct_per_minute": round(len(correct) / elapsed_minutes, 3) if elapsed_minutes > 0 else None,
                "students_below_80_percent": difficulty_count,
                "progress_success_rate": None,
                "relative_rank": None,
            }
        )
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        by_family[str(summary["fact_family"])].append(summary)
    for family_rows in by_family.values():
        family_rows.sort(key=lambda row: (str(row["assessment_date"]), str(row["assessment_id"])))
        for previous, current in zip(family_rows, family_rows[1:]):
            if previous["success_rate"] is not None and current["success_rate"] is not None:
                current["progress_success_rate"] = round(current["success_rate"] - previous["success_rate"], 6)
    by_assessment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        by_assessment[str(summary["assessment_id"])].append(summary)
    for assessment_rows in by_assessment.values():
        assessment_rows.sort(
            key=lambda row: (
                -(row["success_rate"] if row["success_rate"] is not None else -1),
                row["median_correct_time_ms"] if row["median_correct_time_ms"] is not None else math.inf,
            )
        )
        for rank, row in enumerate(assessment_rows, 1):
            row["relative_rank"] = rank
    return sorted(summaries, key=lambda row: (str(row["assessment_date"]), str(row["fact_family"])))


FACT_FAMILY_COLUMNS = [
    "assessment_id", "assessment_date", "academic_period", "fact_family", "student_count", "item_response_count",
    "answered_count", "success_rate", "mean_correct_time_ms", "median_correct_time_ms", "correct_time_iqr_ms",
    "correct_per_minute", "students_below_80_percent", "progress_success_rate", "relative_rank",
]


def _item_summaries(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _latest_attempt_rows(rows):
        if not int(row["is_practice_item"]):
            fact_key = f"{row['operation_type']}:{row['operand_1']}:{row['operand_2']}:{row['expected_answer']}"
            grouped[(str(row["assessment_id"]), fact_key)].append(row)
    output: list[dict[str, Any]] = []
    for (assessment_id, fact_key), group in grouped.items():
        answered = [row for row in group if row["completion_status"] == "answered"]
        correct = [row for row in answered if row["is_correct"] == 1]
        wrong = [str(row["entered_answer"]) for row in answered if row["is_correct"] == 0]
        wrong_counts = Counter(wrong)
        times = [float(row["total_response_time_ms"]) for row in correct if row["total_response_time_ms"] is not None]
        output.append(
            {
                "assessment_id": assessment_id,
                "fact_key": fact_key,
                "operation_type": group[0]["operation_type"],
                "operand_1": group[0]["operand_1"],
                "operand_2": group[0]["operand_2"],
                "expected_answer": group[0]["expected_answer"],
                "fact_family": group[0]["fact_family"],
                "difficulty_category": group[0]["difficulty_category"],
                "presentation_count": sum(row["completion_status"] != "not_presented" for row in group),
                "answered_count": len(answered),
                "success_rate": round(len(correct) / len(answered), 6) if answered else None,
                "median_correct_time_ms": _round_or_none(_median(times)),
                "correct_time_iqr_ms": _round_or_none(
                    None if not times else float(_quantile(times, 0.75)) - float(_quantile(times, 0.25))
                ),
                "omission_rate": round(sum(row["completion_status"] == "omission" for row in group) / len(group), 6),
                "timeout_rate": round(sum(row["timeout_status"] != "none" for row in group) / len(group), 6),
                "wrong_response_count": len(wrong),
                "most_common_wrong_answers": "|".join(f"{answer}:{count}" for answer, count in wrong_counts.most_common(3)),
                "mean_item_position": round(statistics.fmean(float(row["item_position"]) for row in group), 3),
            }
        )
    return sorted(output, key=lambda row: (str(row["assessment_id"]), str(row["fact_key"])))


ITEM_SUMMARY_COLUMNS = [
    "assessment_id", "fact_key", "operation_type", "operand_1", "operand_2", "expected_answer", "fact_family",
    "difficulty_category", "presentation_count", "answered_count", "success_rate", "median_correct_time_ms",
    "correct_time_iqr_ms", "omission_rate", "timeout_rate", "wrong_response_count", "most_common_wrong_answers",
    "mean_item_position",
]


def _student_longitudinal(summaries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in summaries:
        by_student[str(row["student_export_id"])].append(row)
    for student_id, rows in by_student.items():
        rows.sort(key=lambda row: (str(row["assessment_date"]), str(row["assessment_id"])))
        first, last = rows[0], rows[-1]
        x = list(range(len(rows)))
        accuracy_values = [row["success_rate"] for row in rows]
        time_values = [row["median_correct_time_ms"] for row in rows]
        def slope(values: Sequence[float | None]) -> float | None:
            valid = [(float(x_value), float(y_value)) for x_value, y_value in zip(x, values) if y_value is not None]
            if len(valid) < 2:
                return None
            x_mean = statistics.fmean(row[0] for row in valid)
            y_mean = statistics.fmean(row[1] for row in valid)
            denominator = sum((row[0] - x_mean) ** 2 for row in valid)
            return sum((row[0] - x_mean) * (row[1] - y_mean) for row in valid) / denominator if denominator else None
        output.append(
            {
                "student_export_id": student_id,
                "assessment_count": len(rows),
                "first_assessment_date": first["assessment_date"],
                "last_assessment_date": last["assessment_date"],
                "initial_success_rate": first["success_rate"],
                "latest_success_rate": last["success_rate"],
                "success_rate_slope_per_assessment": _round_or_none(slope(accuracy_values), 6),
                "initial_median_correct_time_ms": first["median_correct_time_ms"],
                "latest_median_correct_time_ms": last["median_correct_time_ms"],
                "median_time_slope_ms_per_assessment": _round_or_none(slope(time_values)),
            }
        )
    return output


STUDENT_LONGITUDINAL_COLUMNS = [
    "student_export_id", "assessment_count", "first_assessment_date", "last_assessment_date", "initial_success_rate",
    "latest_success_rate", "success_rate_slope_per_assessment", "initial_median_correct_time_ms",
    "latest_median_correct_time_ms", "median_time_slope_ms_per_assessment",
]


def _class_longitudinal(student_summaries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in student_summaries:
        grouped[(str(row["assessment_id"]), str(row["assessment_date"]))].append(row)
    output = []
    for (assessment_id, assessment_date), group in grouped.items():
        rates = [row["success_rate"] for row in group if row["success_rate"] is not None]
        times = [row["median_correct_time_ms"] for row in group if row["median_correct_time_ms"] is not None]
        output.append(
            {
                "assessment_id": assessment_id,
                "assessment_date": assessment_date,
                "student_count": len(group),
                "median_student_success_rate": _round_or_none(_median(rates), 6),
                "iqr_student_success_rate": _round_or_none(
                    None if not rates else float(_quantile(rates, 0.75)) - float(_quantile(rates, 0.25)), 6
                ),
                "median_student_correct_time_ms": _round_or_none(_median(times)),
                "iqr_student_correct_time_ms": _round_or_none(
                    None if not times else float(_quantile(times, 0.75)) - float(_quantile(times, 0.25))
                ),
            }
        )
    return sorted(output, key=lambda row: (str(row["assessment_date"]), str(row["assessment_id"])))


CLASS_LONGITUDINAL_COLUMNS = [
    "assessment_id", "assessment_date", "student_count", "median_student_success_rate", "iqr_student_success_rate",
    "median_student_correct_time_ms", "iqr_student_correct_time_ms",
]


def _public_aggregate(rows: Sequence[dict[str, Any]], minimum_group_size: int = 5) -> list[dict[str, Any]]:
    """Agrège les résultats et écarte les groupes de moins de cinq élèves."""

    assessments = sorted({(str(row["assessment_date"]), str(row["assessment_id"])) for row in rows})
    session_numbers = {assessment_id: index + 1 for index, (_, assessment_id) in enumerate(assessments)}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _latest_attempt_rows(rows):
        if not int(row["is_practice_item"]):
            grouped[(str(row["assessment_id"]), str(row["fact_family"]))].append(row)
    output = []
    for (assessment_id, family), group in grouped.items():
        students = {str(row["student_export_id"]) for row in group}
        if len(students) < minimum_group_size:
            continue
        answered = [row for row in group if row["completion_status"] == "answered"]
        correct = [row for row in answered if row["is_correct"] == 1]
        times = [float(row["total_response_time_ms"]) for row in correct if row["total_response_time_ms"] is not None]
        accuracy = len(correct) / len(answered) if answered else None
        median_time = _median(times)
        output.append(
            {
                "session_number": session_numbers[assessment_id],
                "fact_family": family,
                "student_count_band": "5-9" if len(students) < 10 else "10-19" if len(students) < 20 else "20+",
                "response_count_rounded_5": int(5 * round(len(group) / 5)),
                "success_rate_rounded_5_percent": None if accuracy is None else int(5 * round(accuracy * 100 / 5)),
                "median_correct_time_rounded_250_ms": None if median_time is None else int(250 * round(median_time / 250)),
                "transformation_note": "Dates supprimées; identifiants individuels supprimés; petits groupes supprimés; valeurs arrondies.",
            }
        )
    return output


PUBLIC_COLUMNS = [
    "session_number", "fact_family", "student_count_band", "response_count_rounded_5",
    "success_rate_rounded_5_percent", "median_correct_time_rounded_250_ms", "transformation_note",
]


def _assessment_items(
    db: Database,
    assessment_id: int | None = None,
    assessment_ids: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    conditions = ["a.deleted_at IS NULL"]
    params: list[Any] = []
    if assessment_id is not None and assessment_ids is not None:
        raise ValueError("Indiquez un seul des deux paramètres assessment_id et assessment_ids.")
    if assessment_id is not None:
        conditions.append("a.id=?")
        params.append(assessment_id)
    elif assessment_ids is not None:
        selected = [int(value) for value in assessment_ids]
        if not selected:
            return []
        conditions.append(f"a.id IN ({','.join('?' for _ in selected)})")
        params.extend(selected)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db.q(
        "SELECT a.assessment_uuid,a.assessment_version,a.random_seed,a.items_hash,ai.item_uuid,ai.position,ai.kind,"
        "ai.is_practice,ai.is_anchor,ai.op,ai.a,ai.b,ai.expected,ai.fact_family,ai.difficulty_category,ai.fact_key "
        f"FROM assessment a JOIN assessment_item ai ON ai.assessment_id=a.id {where} ORDER BY a.id,ai.position",
        tuple(params),
    )
    return [dict(row) for row in rows]


ASSESSMENT_ITEM_COLUMNS = [
    "assessment_uuid", "assessment_version", "random_seed", "items_hash", "item_uuid", "position", "kind",
    "is_practice", "is_anchor", "op", "a", "b", "expected", "fact_family", "difficulty_category", "fact_key",
]


def export_analysis_bundle(
    db: Database,
    output_dir: str,
    assessment_id: int | None = None,
    include_nominative_internal: bool = False,
    assessment_ids: Sequence[int] | None = None,
    *, organized: bool = False,
) -> dict[str, str]:
    """Les noms sont ajoutés à la synthèse enseignant sur demande."""

    root = Path(output_dir)
    destination = root / PUBLIC_DIR / "data" if organized else root
    descriptive = destination
    public = root / PUBLIC_DIR if organized else root
    teacher = root / TEACHER_DIR if organized else root
    destination.mkdir(parents=True, exist_ok=True)
    rows = response_rows(db, assessment_id, assessment_ids)
    student_summaries = _student_summaries(rows)
    copy_rows, copy_summaries = familiarization_rows(db, {str(row["attempt_id"]) for row in rows})
    copy_by_attempt = {row["attempt_id"]: row for row in copy_summaries}
    for summary in student_summaries:
        optional = copy_by_attempt.get(summary["attempt_id"], {})
        summary.update({key: optional.get(key) for key in MEASURE_COLUMNS})
    fact_summaries = _fact_family_summaries(rows)
    item_summaries = _item_summaries(rows)
    outputs = {
        "familiarization_trials": _write_csv(
            destination / "keyboard_familiarization_trials.csv", copy_rows, FAMILIARIZATION_TRIAL_COLUMNS,
        ),
        "familiarization_summary": _write_csv(
            destination / "keyboard_familiarization_summary.csv", copy_summaries, FAMILIARIZATION_SUMMARY_COLUMNS,
        ),
        "responses": _write_csv(destination / "responses_long_pseudonymized.csv", rows, RESPONSE_COLUMNS),
        "students": _write_csv(destination / "student_assessment_summary.csv", student_summaries, STUDENT_SUMMARY_COLUMNS),
        "families": _write_csv(descriptive / "fact_family_summary.csv", fact_summaries, FACT_FAMILY_COLUMNS),
        "items": _write_csv(descriptive / "item_difficulty_summary.csv", item_summaries, ITEM_SUMMARY_COLUMNS),
        "student_longitudinal": _write_csv(
            destination / "student_longitudinal_summary.csv",
            _student_longitudinal(student_summaries),
            STUDENT_LONGITUDINAL_COLUMNS,
        ),
        "class_longitudinal": _write_csv(
            descriptive / "class_longitudinal_summary.csv",
            _class_longitudinal(student_summaries),
            CLASS_LONGITUDINAL_COLUMNS,
        ),
        "public": _write_csv(public / "public_anonymized_dataset.csv", _public_aggregate(rows), PUBLIC_COLUMNS),
        "assessment_items": _write_csv(
            descriptive / "assessment_items_frozen.csv",
            _assessment_items(db, assessment_id, assessment_ids),
            ASSESSMENT_ITEM_COLUMNS,
        ),
    }
    if include_nominative_internal:
        identities = {
            str(row["export_id"]): (str(row["last_name"]), str(row["first_name"]))
            for project in db.q("SELECT id FROM project")
            for row in db.list_students(int(project["id"]))
        }
        nominative_rows = []
        for row in rows:
            last_name, first_name = identities.get(str(row["student_export_id"]), ("", ""))
            nominative_rows.append({"last_name": last_name, "first_name": first_name, **row})
        outputs["nominative_internal"] = _write_csv(
            teacher / "INTERNAL_ONLY_responses_long_nominative.csv",
            nominative_rows,
            ["last_name", "first_name", *RESPONSE_COLUMNS],
        )
        nominative_summaries = []
        for row in student_summaries:
            last_name, first_name = identities.get(str(row["student_export_id"]), ("", ""))
            nominative_summaries.append({"last_name": last_name, "first_name": first_name, **row})
        outputs["nominative_student_summary_internal"] = _write_csv(
            teacher / "INTERNAL_ONLY_student_assessment_summary_nominative.csv",
            nominative_summaries,
            ["last_name", "first_name", *STUDENT_SUMMARY_COLUMNS],
        )
    db.audit(
        "export_created",
        "assessment",
        assessment_id if assessment_id is not None else "selection" if assessment_ids is not None else "all",
        {
            "nominative_internal": include_nominative_internal,
            "output_dir": str(destination.resolve()),
            "assessment_ids": list(assessment_ids) if assessment_ids is not None else None,
        },
    )
    return outputs


def export_assessment_stats_csv(db: Database, assessment_id: int, output_dir: str) -> str:
    return export_analysis_bundle(db, output_dir, assessment_id)["students"]


def export_item_level_stats_csv(db: Database, assessment_id: int, output_dir: str) -> str:
    return export_analysis_bundle(db, output_dir, assessment_id)["responses"]
