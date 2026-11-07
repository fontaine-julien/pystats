"""Préparation des données et lancement des analyses R."""

from __future__ import annotations

import hashlib
import csv
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Sequence

from app.export import DESCRIPTIVE_DIR, PUBLIC_DIR, TEACHER_DIR, export_analysis_bundle
from app.timing import utc_now_iso
from app.version import SOFTWARE_VERSION


BASE_DIR = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = BASE_DIR / "analysis"
RUN_ALL_SCRIPT = ANALYSIS_DIR / "run_all.R"


def find_rscript_executable() -> str:
    configured = os.environ.get("R_SCRIPT", "").strip()
    return configured or "Rscript"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_analysis_outputs(
    db,
    assessment_id: int,
    output_dir: str,
    assessment_ids: Sequence[int] | None = None,
    include_nominative_final_labels: bool = False,
) -> dict[str, Any]:
    """Utilise la première évaluation comme référence et l’évaluation choisie comme cible."""

    destination = Path(output_dir).resolve()
    data_dir = destination / PUBLIC_DIR / "data"
    r_output_dir = destination / PUBLIC_DIR / "results"
    destination.mkdir(parents=True, exist_ok=True)
    selected_ids = list(dict.fromkeys(int(value) for value in (assessment_ids or [assessment_id])))
    placeholders = ",".join("?" for _ in selected_ids)
    assessment_rows = db.q(
        "SELECT id,assessment_uuid,assessment_date,project_id FROM assessment "
        f"WHERE id IN ({placeholders}) AND deleted_at IS NULL ORDER BY assessment_date,id",
        tuple(selected_ids),
    )
    if len(assessment_rows) != len(selected_ids):
        raise ValueError("Une évaluation sélectionnée est introuvable ou supprimée")
    if len({int(row["project_id"]) for row in assessment_rows}) != 1:
        raise ValueError("Toutes les évaluations sélectionnées doivent appartenir au même projet")
    ordered_ids = [int(row["id"]) for row in assessment_rows]
    if assessment_id not in ordered_ids:
        raise ValueError("L’évaluation finale doit appartenir à la sélection")
    focus_uuid = str(next(row["assessment_uuid"] for row in assessment_rows if int(row["id"]) == assessment_id))
    baseline_uuid = str(assessment_rows[0]["assessment_uuid"])
    selected_uuids = [str(row["assessment_uuid"]) for row in assessment_rows]
    export_paths = export_analysis_bundle(
        db,
        str(destination),
        assessment_id=None,
        include_nominative_internal=include_nominative_final_labels,
        assessment_ids=ordered_ids,
        organized=True,
    )
    command = [
        find_rscript_executable(),
        str(RUN_ALL_SCRIPT),
        str(data_dir),
        str(r_output_dir),
        focus_uuid,
        baseline_uuid,
        str(destination / DESCRIPTIVE_DIR),
    ]
    teacher_dir = destination / TEACHER_DIR
    if include_nominative_final_labels:
        command.append(export_paths["nominative_student_summary_internal"])
    try:
        process = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=600,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "Rscript est introuvable. Installez R ou définissez R_SCRIPT avec le chemin complet vers Rscript."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("L’analyse R a dépassé la limite de 10 minutes.") from error
    execution_log = destination / "python_r_execution.log"
    execution_log.write_text(
        f"Commande : {command!r}\nCode de retour : {process.returncode}\n\nSortie standard\n{process.stdout}\n\nSortie d’erreur\n{process.stderr}",
        encoding="utf-8",
    )
    if process.returncode != 0:
        message = (process.stderr or process.stdout or "Erreur R sans message").strip()
        raise RuntimeError(f"L’analyse R a échoué (code {process.returncode}).\n{message}")
    nominative_outputs = {}
    if include_nominative_final_labels and (teacher_dir / "final_performance_scatter.html").is_file():
        nominative_outputs = {
            "nominative_final_html": str(teacher_dir / "final_performance_scatter.html"),
            "nominative_final_data": str(teacher_dir / "final_performance_scatter_data.csv"),
        }
    status_path = r_output_dir / "graph_generation_status.csv"
    graph_statuses: list[dict[str, str]] = []
    status_paths = [status_path]
    if include_nominative_final_labels:
        status_paths.append(teacher_dir / "graph_generation_status.csv")
    for report in status_paths:
        if report.exists():
            with report.open(encoding="utf-8", newline="") as stream:
                graph_statuses.extend(dict(row) for row in csv.DictReader(stream))
    skipped_graphs = [
        {
            "graph_name": row.get("graph_name", "Graphique inconnu"),
            "reason": row.get("reason", "raison non précisée"),
            "comment": row.get("comment", ""),
        }
        for row in graph_statuses
        if row.get("status") != "generated"
    ]
    manifest_path = destination / "MANIFEST.json"
    files = sorted(path for path in destination.rglob("*") if path.is_file() and path != manifest_path)
    manifest: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "software_version": SOFTWARE_VERSION,
        "assessment_id": focus_uuid,
        "baseline_assessment_id": baseline_uuid,
        "selected_assessment_ids": selected_uuids,
        "r_command": command,
        "files": [
            {
                "path": str(path.relative_to(destination)).replace("\\", "/"),
                "sha256": _file_digest(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    db.audit(
        "r_analysis_created",
        "assessment",
        assessment_id,
        {
            "output_dir": str(destination),
            "selected_assessment_ids": ordered_ids,
            "baseline_assessment_id": ordered_ids[0],
            "final_assessment_id": assessment_id,
            "skipped_graph_count": len(skipped_graphs),
            "nominative_final_labels": include_nominative_final_labels,
        },
    )
    return {
        "output_dir": str(destination),
        "class_report": str(r_output_dir / "class_report.pdf"),
        "manifest": str(manifest_path),
        "graph_statuses": graph_statuses,
        "skipped_graphs": skipped_graphs,
        **nominative_outputs,
        **{f"csv_{key}": value for key, value in export_paths.items()},
    }


def generate_graph_pdf(db, assessment_id: int, assessment_title: str = "") -> str:
    del assessment_title
    destination = BASE_DIR / "analysis_outputs" / f"assessment_{assessment_id}"
    return generate_analysis_outputs(
        db,
        assessment_id,
        str(destination),
        assessment_ids=[assessment_id],
    )["class_report"]
