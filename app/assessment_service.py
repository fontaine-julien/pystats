"""Création et gestion des listes d’items figées."""

from __future__ import annotations

from dataclasses import replace
import json
import sqlite3
from typing import Sequence
import uuid

from app.config import AssessmentConfig
from app.db import Database, canonical_hash
from app.itemgen import Item, generate_assessment_items
from app.timing import utc_now_iso
from app.version import SOFTWARE_VERSION


def _source_anchors(db: Database, config: AssessmentConfig) -> list[Item]:
    """Charge les items réutilisables d’une évaluation antérieure."""

    if not config.anchor_count:
        return []
    if not config.anchor_source_assessment_id:
        raise ValueError("Choisissez une évaluation source pour les items d’ancrage.")
    source = db.q(
        "SELECT id FROM assessment WHERE id=? AND deleted_at IS NULL",
        (config.anchor_source_assessment_id,),
    )
    if not source:
        raise ValueError("L’évaluation source est introuvable ou supprimée.")
    rows = db.q(
        "SELECT item_uuid,op,a,b,expected,fact_family,difficulty_category,fact_key "
        "FROM assessment_item WHERE assessment_id=? AND evaluated=1 ORDER BY position LIMIT ?",
        (config.anchor_source_assessment_id, config.anchor_count),
    )
    return [
        Item(
            item_id=str(row["item_uuid"]), op=str(row["op"]), operand_1=int(row["a"]),
            operand_2=int(row["b"] or 0), expected=int(row["expected"]), evaluated=True,
            kind="scored", is_anchor=True, fact_family=str(row["fact_family"]),
            difficulty_category=str(row["difficulty_category"]), fact_key=str(row["fact_key"]),
        )
        for row in rows
    ]


def create_assessment(
    db: Database,
    project_id: int,
    title: str,
    config: AssessmentConfig,
    student_ids: Sequence[int] | None = None,
) -> int:
    """Crée et fige une évaluation avec son empreinte."""

    if student_ids is None:
        student_ids = [int(row["id"]) for row in db.list_students(project_id, active_only=True)]
    assessment_uuid = str(uuid.uuid4())
    now = utc_now_iso()
    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO assessment(assessment_uuid,project_id,type,title,config_json,assessment_version,assessment_date,"
            "academic_period,group_id,random_seed,software_version,created_at,frozen_at,items_hash) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
            (
                assessment_uuid, project_id, *_settings(title, config), SOFTWARE_VERSION, now,
            ),
        )
        assessment_id = int(cursor.lastrowid)
        conn.executemany(
            "INSERT INTO assessment_roster(assessment_id,student_id) "
            "SELECT ?, id FROM student WHERE id=? AND project_id=? AND deleted_at IS NULL",
            [(assessment_id, student_id, project_id) for student_id in student_ids],
        )
        _generate_items(db, conn, assessment_id, config)
        items_hash = canonical_hash(db.assessment_items_payload(assessment_id))
        conn.execute("UPDATE assessment SET items_hash=?,frozen_at=? WHERE id=?", (items_hash, now, assessment_id))
    db.audit(
        "assessment_created",
        "assessment",
        assessment_id,
        {"assessment_uuid": assessment_uuid, "random_seed": config.random_seed, "items_hash": items_hash},
    )
    return assessment_id


def _settings(title: str, config: AssessmentConfig) -> tuple:
    if not title.strip():
        raise ValueError("Le nom de l’évaluation est obligatoire.")
    return ("+".join(config.operations), title.strip(), json.dumps(config.to_dict(), ensure_ascii=False, sort_keys=True),
            config.assessment_version, config.assessment_date, config.academic_period, config.group_id, config.random_seed)


def _generate_items(db: Database, conn: sqlite3.Connection, assessment_id: int, config: AssessmentConfig) -> None:
    items = generate_assessment_items(config, _source_anchors(db, config))
    conn.executemany(
        "INSERT INTO assessment_item(assessment_id,item_uuid,idx,position,op,a,b,expected,evaluated,kind,"
        "is_practice,is_anchor,fact_family,difficulty_category,fact_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(assessment_id, item.item_id, pos, pos, item.op, item.operand_1, item.operand_2, item.expected,
          int(item.evaluated), item.kind, int(not item.evaluated), int(item.is_anchor), item.fact_family,
          item.difficulty_category, item.fact_key) for pos, item in enumerate(items)],
    )


def assessment_started(db: Database, assessment_id: int) -> bool:
    return bool(db.q("SELECT 1 FROM attempt WHERE assessment_id=? LIMIT 1", (assessment_id,)))


def update_assessment(db: Database, assessment_id: int, title: str, config: AssessmentConfig) -> None:
    with db.transaction() as conn:
        previous = load_assessment_config(db, assessment_id)
        if assessment_started(db, assessment_id):
            raise ValueError("Paramètres verrouillés depuis la première passation élève.")
        if not db.verify_assessment_integrity(assessment_id):
            raise ValueError("L’empreinte de la liste enregistrée est invalide.")
        conn.execute("UPDATE assessment SET frozen_at=NULL WHERE id=?", (assessment_id,))
        # Les changements de titre ou de durée préservent la liste d’items à l’identique.
        item_settings = ("operations", "operand_1_values", "operand_2_values", "n_scored_items", "n_practice_items",
                         "anchor_count", "anchor_source_assessment_id", "order_mode", "difficulty_categories", "random_seed")
        if any(getattr(previous, field) != getattr(config, field) for field in item_settings):
            conn.execute("DELETE FROM assessment_item WHERE assessment_id=?", (assessment_id,))
            _generate_items(db, conn, assessment_id, config)
        digest = canonical_hash(db.assessment_items_payload(assessment_id))
        conn.execute(
            "UPDATE assessment SET type=?,title=?,config_json=?,assessment_version=?,assessment_date=?,"
            "academic_period=?,group_id=?,random_seed=?,items_hash=?,frozen_at=? WHERE id=?",
            (*_settings(title, config), digest, utc_now_iso(), assessment_id),
        )
    db.audit("assessment_updated", "assessment", assessment_id, {"items_hash": digest})


def clone_assessment(db: Database, source_id: int, title: str, date: str, period: str) -> int:
    """Copie le protocole, les inscrits et les items dans leur ordre d’origine."""
    with db.transaction() as conn:
        config = replace(load_assessment_config(db, source_id), assessment_date=date, academic_period=period)
        if not db.verify_assessment_integrity(source_id):
            raise ValueError("L’empreinte des items de l’évaluation source est invalide.")
        now = utc_now_iso()
        cursor = conn.execute(
            "INSERT INTO assessment(assessment_uuid,type,title,config_json,assessment_version,assessment_date,"
            "academic_period,group_id,random_seed,project_id,software_version,created_at,items_hash) "
            "SELECT ?,?,?,?,?,?,?,?,?,project_id,software_version,?,items_hash FROM assessment WHERE id=?",
            (str(uuid.uuid4()), *_settings(title, config), now, source_id),
        )
        new_id = int(cursor.lastrowid)
        columns = ("item_uuid,idx,position,op,a,b,expected,evaluated,kind,is_practice,is_anchor,"
                   "fact_family,difficulty_category,fact_key")
        conn.execute(f"INSERT INTO assessment_item(assessment_id,{columns}) "
                     f"SELECT ?,{columns} FROM assessment_item WHERE assessment_id=?", (new_id, source_id))
        conn.execute("INSERT INTO assessment_roster(assessment_id,student_id) SELECT ?,student_id "
                     "FROM assessment_roster JOIN student s ON s.id=student_id "
                     "WHERE assessment_id=? AND s.deleted_at IS NULL", (new_id, source_id))
        conn.execute("UPDATE assessment SET frozen_at=? WHERE id=?", (now, new_id))
    db.audit("assessment_cloned", "assessment", new_id, {"source_assessment_id": source_id})
    return new_id


def load_assessment_config(db: Database, assessment_id: int) -> AssessmentConfig:
    rows = db.q(
        "SELECT config_json,type,assessment_date FROM assessment WHERE id=? AND deleted_at IS NULL",
        (assessment_id,),
    )
    if not rows:
        raise ValueError("Évaluation introuvable.")
    stored = json.loads(str(rows[0]["config_json"]))
    stored.setdefault("assessment_date", rows[0]["assessment_date"])
    stored.setdefault("type", rows[0]["type"])
    return AssessmentConfig.from_dict(stored)
