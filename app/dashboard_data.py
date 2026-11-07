"""Seule la dernière passation valide de chaque élève compte par évaluation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean, median

from app.schema import ELIGIBLE_ATTEMPT_SQL


@dataclass(frozen=True)
class Result:
    assessment_id: int
    student_id: int
    attempt_id: int
    total: int
    answered: int
    correct: int
    omitted: int
    timeout: int
    not_presented: int
    seconds: float | None
    mean_correct: float | None = None
    mean_wrong: float | None = None
    mean_answered: float | None = None
    timed_count: int = 0

    @property
    def accuracy(self) -> float | None:
        return 100 * self.correct / self.answered if self.answered else None


@dataclass
class Snapshot:
    assessments: list[dict]
    results: list[Result]
    roster: dict[int, set[int]]
    excluded: int

    def selected(self, assessment_id: int | None) -> list[Result]:
        return [r for r in self.results if assessment_id is None or r.assessment_id == assessment_id]


def load_cached_snapshot(connection, project_id: int) -> Snapshot | None:
    cached = connection.execute("SELECT payload FROM dashboard_cache WHERE project_id=? AND version=1",
                                (project_id,)).fetchone()
    if cached:
        try:
            data = json.loads(cached[0])
            return Snapshot(data["assessments"], [Result(**r) for r in data["results"]],
                            {int(k): set(v) for k, v in data["roster"].items()}, data["excluded"])
        except (ValueError, KeyError, TypeError):
            pass  # Recalcule à partir des réponses brutes.
    return None


def build_snapshot(path: str, project_id: int, *, use_cache=False) -> Snapshot:
    """Lit un instantané cohérent et réutilise les calculs en cache si possible."""
    mode = "rw" if use_cache else "ro"
    connection = sqlite3.connect(Path(path).resolve().as_uri() + f"?mode={mode}", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        if use_cache:
            cached = load_cached_snapshot(connection, project_id)
            if cached:
                return cached
        assessments = [dict(row) for row in connection.execute(
            "SELECT id,title,assessment_date,config_json FROM assessment "
            "WHERE project_id=? AND deleted_at IS NULL ORDER BY assessment_date,id", (project_id,))]
        roster: dict[int, set[int]] = defaultdict(set)
        for row in connection.execute(
            "SELECT ar.assessment_id,ar.student_id FROM assessment_roster ar "
            "JOIN student s ON s.id=ar.student_id AND s.deleted_at IS NULL "
            "JOIN assessment a ON a.id=ar.assessment_id WHERE a.project_id=? AND a.deleted_at IS NULL",
            (project_id,)):
            roster[row["assessment_id"]].add(row["student_id"])
        attempts = list(connection.execute(
            f"SELECT att.*, ({ELIGIBLE_ATTEMPT_SQL}) AS eligible FROM attempt att JOIN assessment a ON a.id=att.assessment_id "
            "JOIN student s ON s.id=att.student_id AND s.deleted_at IS NULL "
            "WHERE a.project_id=? AND a.deleted_at IS NULL ORDER BY att.id", (project_id,)))
        latest = {}
        excluded = 0
        for row in attempts:
            if row["eligible"]:
                latest[(row["assessment_id"], row["student_id"])] = row
            else:
                excluded += 1
        # Le filtre SQL évite de charger les identités et les journaux de touches.
        items = connection.execute(
            "SELECT att.id AS attempt_id,ai.id AS item_id,ar.completion_status,ar.correct,"
            "ar.total_response_time_ms FROM attempt att "
            "JOIN assessment a ON a.id=att.assessment_id "
            "JOIN attempt_item ai ON ai.attempt_id=att.id "
            "LEFT JOIN attempt_response ar ON ar.attempt_item_id=ai.id "
            "WHERE a.project_id=? AND a.deleted_at IS NULL AND ai.evaluated=1 "
            f"AND ai.is_practice=0 AND {ELIGIBLE_ATTEMPT_SQL}", (project_id,))
        chosen = {row["id"] for row in latest.values()}
        groups = defaultdict(list)
        for row in items:
            if row["attempt_id"] in chosen:
                groups[row["attempt_id"]].append(row)
        results = []
        for (assessment_id, student_id), attempt in latest.items():
            group = groups[attempt["id"]]
            if not group:
                continue
            answered = [r for r in group if r["completion_status"] == "answered"]
            correct = [r for r in answered if r["correct"] == 1]
            timed = [(r["correct"], r["total_response_time_ms"] / 1000) for r in answered
                     if r["total_response_time_ms"] is not None
                     and math.isfinite(r["total_response_time_ms"]) and r["total_response_time_ms"] > 0]
            times = [t for outcome, t in timed if outcome == 1]
            wrong = [t for outcome, t in timed if outcome == 0]
            results.append(Result(
                assessment_id, student_id, attempt["id"], len(group), len(answered), len(correct),
                sum(r["completion_status"] == "omission" for r in group),
                sum(r["completion_status"] == "timeout" for r in group),
                sum(r["completion_status"] in (None, "not_presented") for r in group),
                median(times) if times else None, mean(times) if times else None,
                mean(wrong) if wrong else None, mean(t for _, t in timed) if timed else None, len(timed)))
        if use_cache:
            payload = json.dumps(dict(assessments=assessments, results=[asdict(r) for r in results],
                                      roster={k: sorted(v) for k, v in roster.items()}, excluded=excluded))
            try:
                connection.execute("INSERT OR REPLACE INTO dashboard_cache VALUES (?,1,?)", (project_id, payload))
                connection.commit()
            except sqlite3.OperationalError as exc:
                if (exc.sqlite_errorcode & 255) not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise
                # Une écriture concurrente a invalidé les résultats lus.
        return Snapshot(assessments, results, dict(roster), excluded)
    finally:
        connection.close()


def median_value(rows: list[Result], metric: str) -> float | None:
    values = [getattr(row, metric) for row in rows if getattr(row, metric) is not None]
    return median(values) if values else None


def ranking(rows: list[Result], metric: str) -> list[tuple[int, Result]]:
    """Les ex æquo partagent le même rang (1, 1, 3)."""
    valid = sorted((r for r in rows if getattr(r, metric) is not None),
                   key=lambda r: getattr(r, metric), reverse=metric == "accuracy")
    output = []
    last_value = None
    rank = 0
    for index, row in enumerate(valid, 1):
        value = getattr(row, metric)
        if value != last_value:
            rank = index
        output.append((rank, row))
        last_value = value
    return output


def median_center(rows: list[Result]) -> tuple[float, float] | None:
    """Médiane par axe sur au moins trois élèves disposant des deux mesures."""
    paired = [r for r in rows if r.seconds is not None and r.accuracy is not None]
    if len(paired) < 3:
        return None
    return median(r.seconds for r in paired), median(r.accuracy for r in paired)
