"""Mesures pseudonymisées de familiarisation au pavé numérique."""

from __future__ import annotations

from collections import defaultdict
import json
import statistics

from app.db import Database


IDENTITY_COLUMNS = ["assessment_id", "assessment_date", "student_export_id", "attempt_id"]
TIMING_COLUMNS = ["reaction_time_first_key_ms", "typing_time_ms", "total_response_time_ms"]
MEASURE_COLUMNS = [
    "familiarization_enabled", "familiarization_protocol", "familiarization_status",
    "familiarization_measured_presented", "familiarization_measured_correct",
    "familiarization_measured_incorrect", "familiarization_measured_omissions",
    "familiarization_measured_timeouts", "familiarization_measured_corrections",
    *[name for digits in (1, 2) for name in (
        f"familiarization_{digits}digit_valid_count",
        *(f"familiarization_{digits}digit_median_{timing}" for timing in TIMING_COLUMNS),
    )],
]
SUMMARY_COLUMNS = IDENTITY_COLUMNS + MEASURE_COLUMNS
TRIAL_COLUMNS = IDENTITY_COLUMNS + [
    "protocol", "position", "phase", "target", "initial_text", "raw_answer_text",
    "is_correct", "completion_status", "presented_at", "first_key_at", "validated_at",
    *TIMING_COLUMNS, "keystroke_count", "correction_count", "event_json", "software_version",
]


def familiarization_rows(db: Database, attempt_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """Inclut les passations pour lesquelles la familiarisation était désactivée."""
    trials_by_attempt = defaultdict(list)
    raw_rows = []
    for row in db.q(
        "SELECT t.*,att.attempt_uuid FROM familiarization_trial t "
        "JOIN attempt att ON att.id=t.attempt_id ORDER BY att.id,t.position"
    ):
        if row["attempt_uuid"] in attempt_ids:
            trials_by_attempt[row["attempt_uuid"]].append(dict(row))
    summaries = []
    for attempt in db.q(
        "SELECT a.assessment_uuid,a.assessment_date,a.config_json,att.attempt_uuid,att.ended_reason,s.export_id "
        "FROM attempt att JOIN assessment a ON a.id=att.assessment_id "
        "JOIN student s ON s.id=att.student_id WHERE a.deleted_at IS NULL ORDER BY a.id,att.id"
    ):
        if attempt["attempt_uuid"] not in attempt_ids:
            continue
        identity = dict(zip(IDENTITY_COLUMNS, (
            attempt["assessment_uuid"], attempt["assessment_date"], attempt["export_id"], attempt["attempt_uuid"],
        )))
        config = json.loads(attempt["config_json"] or "{}")
        enabled = bool(config.get("familiarization_enabled", False))
        trials = trials_by_attempt[attempt["attempt_uuid"]]
        measured = []
        responses = []
        for trial in trials:
            response = json.loads(trial["response_json"]) if trial["response_json"] else {}
            responses.append(response)
            raw = {
                **identity, **{key: trial[key] for key in ("protocol", "position", "phase", "target", "initial_text")},
                **response,
                "is_correct": int(response["is_correct"]) if response.get("is_correct") is not None else None,
                "completion_status": response.get("completion_status", "not_presented"),
                "event_json": json.dumps(response.get("events", []), ensure_ascii=False),
            }
            raw_rows.append(raw)
            if trial["phase"] == "measured":
                measured.append(raw)
        if not enabled:
            status = "disabled"
        elif len(responses) == 15 and all(r and r["completion_status"] != "interrupted" for r in responses):
            status = "completed"
        elif not any(responses):
            status = "not_started"
        else:
            status = "in_progress" if attempt["ended_reason"] == "in_progress" else "incomplete"
        summary = {**identity, **dict.fromkeys(MEASURE_COLUMNS)}
        summary.update(
            familiarization_enabled=int(enabled), familiarization_status=status,
            familiarization_protocol=config.get("familiarization_protocol", "numpad_copy_v1") if enabled else None,
        )
        if enabled:
            summary.update({
                "familiarization_measured_presented": sum(r["completion_status"] != "not_presented" for r in measured),
                "familiarization_measured_correct": sum(r["is_correct"] == 1 for r in measured),
                "familiarization_measured_incorrect": sum(r["is_correct"] == 0 for r in measured),
                "familiarization_measured_omissions": sum(r["completion_status"] == "omission" for r in measured),
                "familiarization_measured_timeouts": sum(r["completion_status"] == "timeout" for r in measured),
                "familiarization_measured_corrections": sum(r.get("correction_count", 0) for r in measured),
            })
            for digits in (1, 2):
                valid = [r for r in measured if len(r["target"]) == digits and r["is_correct"] == 1
                         and r.get("correction_count") == 0 and all(r.get(c) is not None for c in TIMING_COLUMNS)]
                prefix = f"familiarization_{digits}digit_"
                summary[prefix + "valid_count"] = len(valid)
                for timing in TIMING_COLUMNS:
                    summary[prefix + "median_" + timing] = (
                        round(statistics.median(r[timing] for r in valid), 3) if valid else None
                    )
        summaries.append(summary)
    return raw_rows, summaries
