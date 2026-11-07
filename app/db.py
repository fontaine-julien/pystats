"""Stockage SQLite, migration et contrôle d’intégrité."""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
from typing import Any, Iterable, Iterator, Optional, Sequence
import uuid

from app.schema import CORE_SCHEMA_SQL, IDENTITY_SCHEMA_SQL, IMMUTABILITY_TRIGGERS
from app.familiarization import copy_trials
from app.timing import TimingResult, utc_now_iso
from app.version import SCHEMA_VERSION, SOFTWARE_VERSION


def _canonical_hash(payload: object) -> str:
    """Calcule le SHA-256 d’une représentation JSON stable."""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class Database:
    """Les noms résident dans une base distincte des résultats."""

    def __init__(self, path: Optional[str] = None, automatic_backups: bool = True):
        self.conn: sqlite3.Connection | None = None
        self.path: str | None = None
        self.identity_path: str | None = None
        self.automatic_backups = automatic_backups
        if path:
            self.open(path)

    def open(self, path: str) -> None:
        """Ouvre la base, sauvegarde l’ancienne version si nécessaire et rattache les identités."""

        requested = Path(path).expanduser().resolve()
        requested.parent.mkdir(parents=True, exist_ok=True)
        self.close()
        if requested.exists() and requested.stat().st_size:
            self._make_pre_migration_backup_if_needed(requested)
        self.conn = sqlite3.connect(str(requested), timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = FULL")
        self.path = str(requested)
        identity_dir = requested.parent / "_identities"
        identity_dir.mkdir(parents=True, exist_ok=True)
        identity_path = identity_dir / f"{requested.stem}.identities.sqlite"
        self.identity_path = str(identity_path)
        self.conn.execute("ATTACH DATABASE ? AS identity", (self.identity_path,))
        self.conn.executescript(IDENTITY_SCHEMA_SQL)
        self._migrate()
        self._migrate_legacy_identities()
        self._protect_identity_file(identity_path)
        self.set_meta("schema_version", str(SCHEMA_VERSION))
        self.set_meta("software_version", SOFTWARE_VERSION)

    def _make_pre_migration_backup_if_needed(self, source: Path) -> None:
        """Sauvegarde la base avant sa première migration."""

        try:
            probe = sqlite3.connect(str(source))
            tables = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = None
            if "meta" in tables:
                row = probe.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                version = row[0] if row else None
            probe.close()
        except sqlite3.Error:
            return
        if version == str(SCHEMA_VERSION):
            return
        backup_dir = source.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        destination = backup_dir / (
            f"{source.stem}_before_v{SCHEMA_VERSION}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite"
        )
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as live:
            with closing(sqlite3.connect(destination)) as backup:
                live.backup(backup)

    @staticmethod
    def _protect_identity_file(path: Path) -> None:
        """Restreint les droits au propriétaire sur les systèmes compatibles."""

        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Les droits POSIX peuvent être ignorés sous Windows ou sur un lecteur réseau.
            pass

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.commit()
                self.conn.close()
            finally:
                self.conn = None
        self.path = None
        self.identity_path = None

    def q(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        if self.conn is None:
            raise RuntimeError("La base de données est fermée.")
        return self.conn.execute(sql, params).fetchall()

    def exec(self, sql: str, params: Sequence[Any] = ()) -> int:
        if self.conn is None:
            raise RuntimeError("La base de données est fermée.")
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return int(cursor.lastrowid or 0)

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> None:
        """Exécute le lot dans une seule transaction."""

        if self.conn is None:
            raise RuntimeError("La base de données est fermée.")
        with self.transaction():
            self.conn.executemany(sql, list(seq_of_params))

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Prend le verrou d’écriture au début de la transaction."""

        if self.conn is None:
            raise RuntimeError("La base de données est fermée.")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_meta(self, key: str) -> Optional[str]:
        rows = self.q("SELECT value FROM meta WHERE key=?", (key,))
        return None if not rows else str(rows[0]["value"])

    def set_meta(self, key: str, value: str) -> None:
        self.exec(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def _table_columns(self, table: str) -> set[str]:
        return {str(row["name"]) for row in self.q(f"PRAGMA table_info({table})")}

    def _add_column_if_missing(self, table: str, definition: str, name: str) -> None:
        if name not in self._table_columns(table):
            assert self.conn is not None
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def _migrate(self) -> None:
        """Migre les anciens schémas en conservant leurs données."""

        assert self.conn is not None
        self.conn.executescript(CORE_SCHEMA_SQL)
        # Le verrou reste acquis jusqu’au rétablissement des protections. Un échec annule aussi les changements de déclencheurs.
        with self.transaction() as conn:
            for name in IMMUTABILITY_TRIGGERS:
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            self._backfill_schema()
            for name, definition in IMMUTABILITY_TRIGGERS.items():
                conn.execute(f"CREATE TRIGGER {name} {definition}")
            conn.execute("CREATE TABLE IF NOT EXISTS dashboard_cache "
                         "(project_id INTEGER PRIMARY KEY, version INTEGER, payload TEXT NOT NULL)")
            # Le cache est invalidé dans la même transaction, même si une ancienne version écrit dans la base.
            for table, columns in {
                "student": ("id", "deleted_at"),
                "assessment": ("id", "project_id", "title", "assessment_date", "config_json", "deleted_at"),
                "assessment_roster": ("assessment_id", "student_id"),
                "attempt": ("id", "assessment_id", "student_id", "finished_at", "ended_reason"),
                "attempt_item": ("id", "attempt_id", "evaluated", "is_practice"),
                "attempt_response": ("attempt_item_id", "completion_status", "correct", "total_response_time_ms"),
            }.items():
                changed = " OR ".join(f"OLD.{key} IS NOT NEW.{key}" for key in columns)
                for event in ("INSERT", "DELETE", "UPDATE"):
                    condition = f"WHEN {changed}" if event == "UPDATE" else ""
                    conn.execute(f"CREATE TRIGGER IF NOT EXISTS dashboard_{table}_{event} AFTER {event} "
                                 f"ON {table} {condition} BEGIN DELETE FROM dashboard_cache; END")

    def _backfill_schema(self) -> None:
        assert self.conn is not None
        additions: dict[str, list[tuple[str, str]]] = {
            "project": [("created_at TEXT", "created_at")],
            "student": [
                ("deleted_at TEXT", "deleted_at"),
                ("active INTEGER NOT NULL DEFAULT 1", "active"),
                ("export_id TEXT", "export_id"),
                ("group_id TEXT NOT NULL DEFAULT 'classe'", "group_id"),
            ],
            "assessment": [
                ("assessment_uuid TEXT", "assessment_uuid"),
                ("title TEXT NOT NULL DEFAULT ''", "title"),
                ("config_json TEXT NOT NULL DEFAULT '{}'", "config_json"),
                ("assessment_version TEXT NOT NULL DEFAULT '1'", "assessment_version"),
                ("assessment_date TEXT", "assessment_date"),
                ("academic_period TEXT NOT NULL DEFAULT ''", "academic_period"),
                ("group_id TEXT NOT NULL DEFAULT 'classe'", "group_id"),
                ("random_seed INTEGER", "random_seed"),
                ("software_version TEXT", "software_version"),
                ("created_at TEXT", "created_at"),
                ("frozen_at TEXT", "frozen_at"),
                ("items_hash TEXT", "items_hash"),
                ("deleted_at TEXT", "deleted_at"),
                ("deletion_reason TEXT", "deletion_reason"),
            ],
            "assessment_item": [
                ("item_uuid TEXT", "item_uuid"),
                ("position INTEGER", "position"),
                ("op TEXT NOT NULL DEFAULT 'multiplication'", "op"),
                ("b INTEGER NOT NULL DEFAULT 0", "b"),
                ("kind TEXT NOT NULL DEFAULT 'scored'", "kind"),
                ("is_practice INTEGER NOT NULL DEFAULT 0", "is_practice"),
                ("is_anchor INTEGER NOT NULL DEFAULT 0", "is_anchor"),
                ("fact_family TEXT NOT NULL DEFAULT ''", "fact_family"),
                ("difficulty_category TEXT NOT NULL DEFAULT ''", "difficulty_category"),
                ("fact_key TEXT NOT NULL DEFAULT ''", "fact_key"),
            ],
            "attempt": [
                ("attempt_uuid TEXT", "attempt_uuid"),
                ("finished_at TEXT", "finished_at"),
                ("duration_ms REAL", "duration_ms"),
                ("ended_reason TEXT", "ended_reason"),
                ("items_presented INTEGER NOT NULL DEFAULT 0", "items_presented"),
                ("items_answered INTEGER NOT NULL DEFAULT 0", "items_answered"),
                ("items_correct INTEGER NOT NULL DEFAULT 0", "items_correct"),
                ("items_incorrect INTEGER NOT NULL DEFAULT 0", "items_incorrect"),
                ("items_timeout INTEGER NOT NULL DEFAULT 0", "items_timeout"),
                ("items_omitted INTEGER NOT NULL DEFAULT 0", "items_omitted"),
                ("items_not_presented INTEGER NOT NULL DEFAULT 0", "items_not_presented"),
                ("software_version TEXT", "software_version"),
                ("integrity_hash TEXT", "integrity_hash"),
            ],
            "attempt_item": [
                ("item_uuid TEXT", "item_uuid"),
                ("position INTEGER", "position"),
                ("op TEXT NOT NULL DEFAULT 'multiplication'", "op"),
                ("b INTEGER NOT NULL DEFAULT 0", "b"),
                ("kind TEXT NOT NULL DEFAULT 'scored'", "kind"),
                ("is_practice INTEGER NOT NULL DEFAULT 0", "is_practice"),
                ("is_anchor INTEGER NOT NULL DEFAULT 0", "is_anchor"),
                ("fact_family TEXT NOT NULL DEFAULT ''", "fact_family"),
                ("difficulty_category TEXT NOT NULL DEFAULT ''", "difficulty_category"),
                ("fact_key TEXT NOT NULL DEFAULT ''", "fact_key"),
            ],
            "attempt_response": [
                ("presented_at TEXT", "presented_at"),
                ("first_key_at TEXT", "first_key_at"),
                ("validated_at TEXT", "validated_at"),
                ("raw_answer_text TEXT", "raw_answer_text"),
                ("reaction_time_first_key_ms REAL", "reaction_time_first_key_ms"),
                ("typing_time_ms REAL", "typing_time_ms"),
                ("total_response_time_ms REAL", "total_response_time_ms"),
                ("keystroke_count INTEGER NOT NULL DEFAULT 0", "keystroke_count"),
                ("correction_count INTEGER NOT NULL DEFAULT 0", "correction_count"),
                ("timeout_status TEXT NOT NULL DEFAULT 'none'", "timeout_status"),
                ("completion_status TEXT NOT NULL DEFAULT 'answered'", "completion_status"),
                ("event_json TEXT NOT NULL DEFAULT '[]'", "event_json"),
                ("software_version TEXT", "software_version"),
                ("record_hash TEXT", "record_hash"),
                ("created_at TEXT", "created_at"),
            ],
        }
        for table, definitions in additions.items():
            for definition, name in definitions:
                self._add_column_if_missing(table, definition, name)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assessment_active ON assessment(project_id, deleted_at)"
        )

        now = utc_now_iso()
        self.conn.execute("UPDATE project SET created_at=COALESCE(created_at, ?)", (now,))
        self.conn.execute("UPDATE assessment SET created_at=COALESCE(created_at, ?)", (now,))
        for row in self.conn.execute("SELECT id FROM assessment WHERE assessment_uuid IS NULL OR assessment_uuid='' "):
            self.conn.execute("UPDATE assessment SET assessment_uuid=? WHERE id=?", (str(uuid.uuid4()), row["id"]))
        for table in ("assessment_item", "attempt_item"):
            self.conn.execute(f"UPDATE {table} SET position=COALESCE(position, idx)")
            self.conn.execute(f"UPDATE {table} SET is_practice=CASE WHEN kind IN ('example','trial','practice') THEN 1 ELSE is_practice END")
            for row in self.conn.execute(f"SELECT id, op, a, b, expected FROM {table} WHERE item_uuid IS NULL OR item_uuid='' "):
                item_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"legacy:{table}:{row['id']}"))
                fact_key = f"{row['op']}:{row['a']}:{row['b']}:{row['expected']}"
                self.conn.execute(
                    f"UPDATE {table} SET item_uuid=?, fact_key=CASE WHEN fact_key='' THEN ? ELSE fact_key END WHERE id=?",
                    (item_uuid, fact_key, row["id"]),
                )
        for row in self.conn.execute("SELECT id FROM attempt WHERE attempt_uuid IS NULL OR attempt_uuid='' "):
            self.conn.execute("UPDATE attempt SET attempt_uuid=? WHERE id=?", (str(uuid.uuid4()), row["id"]))
        self.conn.execute("UPDATE assessment SET assessment_date=COALESCE(assessment_date, substr(created_at,1,10))")
        self.conn.execute("UPDATE assessment SET software_version=COALESCE(software_version, 'legacy')")
        self.conn.execute("UPDATE attempt SET software_version=COALESCE(software_version, 'legacy')")
        self.conn.execute("UPDATE attempt_response SET created_at=COALESCE(created_at, responded_at, validated_at, ?)", (now,)) if "responded_at" in self._table_columns("attempt_response") else self.conn.execute("UPDATE attempt_response SET created_at=COALESCE(created_at, validated_at, ?)", (now,))
        for row in self.conn.execute("SELECT id FROM assessment WHERE items_hash IS NULL OR items_hash='' ").fetchall():
            payload = self.assessment_items_payload(int(row["id"]))
            if payload:
                self.conn.execute("UPDATE assessment SET items_hash=? WHERE id=?", (_canonical_hash(payload), row["id"]))
        self.conn.execute("UPDATE assessment SET frozen_at=created_at WHERE frozen_at IS NULL")

    def _migrate_legacy_identities(self) -> None:
        """Déplace les noms dans la base d’identités et les efface de la base analytique."""

        assert self.conn is not None
        rows = self.conn.execute(
            "SELECT id, project_id, last_name, first_name, export_id FROM student ORDER BY id"
        ).fetchall()
        with self.transaction() as conn:
            for row in rows:
                export_id = str(row["export_id"] or f"STU-{secrets.token_hex(5).upper()}")
                existing = conn.execute(
                    "SELECT last_name, first_name FROM identity.student_identity WHERE student_id=?",
                    (row["id"],),
                ).fetchone()
                last_name = str(row["last_name"] or (existing["last_name"] if existing else ""))
                first_name = str(row["first_name"] or (existing["first_name"] if existing else ""))
                conn.execute(
                    "INSERT INTO identity.student_identity(student_id,project_id,last_name,first_name,internal_export_id,created_at) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET "
                    "project_id=excluded.project_id,last_name=CASE WHEN excluded.last_name<>'' THEN excluded.last_name ELSE student_identity.last_name END,"
                    "first_name=CASE WHEN excluded.first_name<>'' THEN excluded.first_name ELSE student_identity.first_name END,"
                    "internal_export_id=excluded.internal_export_id",
                    (row["id"], row["project_id"], last_name, first_name, export_id, utc_now_iso()),
                )
                conn.execute("UPDATE student SET last_name='', first_name='', export_id=? WHERE id=?", (export_id, row["id"]))

    def create_student(
        self,
        project_id: int,
        last_name: str,
        first_name: str,
        group_id: str = "classe",
    ) -> int:
        """Crée l’élève avec un pseudonyme aléatoire stable."""

        export_id = f"STU-{secrets.token_hex(5).upper()}"
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO student(project_id,last_name,first_name,active,export_id,group_id) VALUES(?,?,?,?,?,?)",
                (project_id, "", "", 1, export_id, group_id or "classe"),
            )
            student_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO identity.student_identity(student_id,project_id,last_name,first_name,internal_export_id,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (student_id, project_id, last_name.strip(), first_name.strip(), export_id, utc_now_iso()),
            )
        return student_id

    def list_students(
        self,
        project_id: int,
        active_only: bool = False,
        student_ids: Sequence[int] | None = None,
    ) -> list[sqlite3.Row]:
        conditions = ["s.project_id=?", "s.deleted_at IS NULL"]
        params: list[Any] = [project_id]
        if active_only:
            conditions.append("s.active=1")
        if student_ids is not None:
            if not student_ids:
                return []
            conditions.append(f"s.id IN ({','.join('?' for _ in student_ids)})")
            params.extend(student_ids)
        return self.q(
            "SELECT s.id,s.project_id,s.active,s.export_id,s.group_id,i.last_name,i.first_name "
            "FROM student s JOIN identity.student_identity i ON i.student_id=s.id "
            f"WHERE {' AND '.join(conditions)} ORDER BY i.last_name,i.first_name",
            tuple(params),
        )

    def get_student_identity(self, student_id: int) -> sqlite3.Row | None:
        rows = self.q(
            "SELECT s.id,s.export_id,s.group_id,i.last_name,i.first_name "
            "FROM student s JOIN identity.student_identity i ON i.student_id=s.id WHERE s.id=?",
            (student_id,),
        )
        return rows[0] if rows else None

    def rename_student(self, student_id: int, last_name: str, first_name: str) -> None:
        last_name, first_name = last_name.strip(), first_name.strip()
        if not last_name or not first_name:
            raise ValueError("Le nom et le prénom sont obligatoires.")
        self.exec("UPDATE identity.student_identity SET last_name=?,first_name=? WHERE student_id=?",
                  (last_name, first_name, student_id))

    def remove_student(self, student_id: int) -> None:
        """Efface définitivement l’élève et ses passations."""
        self._delete_student_data(student_id)

    def delete_student_assessment(self, student_id: int, assessment_id: int) -> None:
        """Efface les passations pour cette évaluation et conserve l’inscription."""
        if assessment_id is None:
            raise ValueError("Sélectionnez une évaluation.")
        self._delete_student_data(student_id, assessment_id)

    def _delete_student_data(self, student_id: int, assessment_id: int | None = None) -> None:
        """Applique la suppression demandée, y compris sur les anciens schémas."""
        with self.transaction() as conn:
            if assessment_id is not None and not conn.execute(
                "SELECT 1 FROM assessment a JOIN student s ON s.project_id=a.project_id "
                "WHERE a.id=? AND s.id=? AND a.deleted_at IS NULL", (assessment_id, student_id)
            ).fetchone():
                raise ValueError("Élève ou évaluation introuvable dans ce projet.")
            attempts = "SELECT id FROM attempt WHERE student_id=?"
            params = [student_id]
            if assessment_id is not None:
                attempts += " AND assessment_id=?"
                params.append(assessment_id)
            items = f"SELECT id FROM attempt_item WHERE attempt_id IN ({attempts})"
            responses = f"SELECT id FROM attempt_response WHERE attempt_item_id IN ({items})"
            # La transaction suspend ces protections le temps de la suppression et les rétablit avant validation.
            guards = conn.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN "
                "('prevent_response_delete','prevent_familiarization_delete')"
            ).fetchall()
            for guard in guards:
                conn.execute(f"DROP TRIGGER {guard['name']}")
            conn.execute(f"DELETE FROM response_key_event WHERE response_id IN ({responses})", params)
            conn.execute(f"DELETE FROM attempt_response WHERE attempt_item_id IN ({items})", params)
            conn.execute(f"DELETE FROM familiarization_trial WHERE attempt_id IN ({attempts})", params)
            conn.execute(f"DELETE FROM attempt_item WHERE attempt_id IN ({attempts})", params)
            conn.execute(
                f"DELETE FROM audit_event WHERE entity_type='attempt' "
                f"AND entity_id IN (SELECT CAST(id AS TEXT) FROM attempt WHERE id IN ({attempts}))", params
            )
            conn.execute(f"DELETE FROM attempt WHERE id IN ({attempts})", params)
            if assessment_id is None:
                conn.execute("DELETE FROM assessment_roster WHERE student_id=?", (student_id,))
                conn.execute("DELETE FROM identity.student_identity WHERE student_id=?", (student_id,))
                conn.execute("DELETE FROM audit_event WHERE entity_type='student' AND entity_id=?", (str(student_id),))
                conn.execute("DELETE FROM student WHERE id=?", (student_id,))
            for guard in guards:
                conn.execute(guard["sql"])

    def audit(self, event_type: str, entity_type: str, entity_id: object, details: dict[str, Any] | None = None) -> None:
        self.exec(
            "INSERT INTO audit_event(occurred_at,event_type,entity_type,entity_id,details_json) VALUES(?,?,?,?,?)",
            (utc_now_iso(), event_type, entity_type, str(entity_id), json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
        )

    def list_assessments(
        self,
        project_id: int | None = None,
        include_deleted: bool = False,
    ) -> list[sqlite3.Row]:
        """Liste les évaluations par date et masque les évaluations supprimées par défaut."""

        conditions: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            conditions.append("project_id=?")
            params.append(project_id)
        if not include_deleted:
            conditions.append("deleted_at IS NULL")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return self.q(
            "SELECT id,assessment_uuid,project_id,title,assessment_date,academic_period,assessment_version,"
            f"deleted_at,deletion_reason FROM assessment {where} "
            "ORDER BY assessment_date,id",
            tuple(params),
        )

    def soft_delete_assessment(self, assessment_id: int, reason: str) -> str:
        """Masque l’évaluation et conserve ses données ainsi que le motif."""

        justification = reason.strip()
        if not justification:
            raise ValueError("Indiquez le motif de la suppression.")
        if self.conn is None:
            raise RuntimeError("La base de données est fermée.")
        deleted_at = utc_now_iso()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT assessment_uuid,title,deleted_at FROM assessment WHERE id=?",
                (assessment_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Évaluation introuvable.")
            if row["deleted_at"] is not None:
                raise ValueError("Cette évaluation a déjà été supprimée.")
            conn.execute(
                "UPDATE assessment SET deleted_at=?,deletion_reason=? WHERE id=?",
                (deleted_at, justification, assessment_id),
            )
            details = {
                "assessment_uuid": str(row["assessment_uuid"]),
                "title": str(row["title"]),
                "reason": justification,
                "deleted_at": deleted_at,
                "retention_mode": "soft_delete",
            }
            conn.execute(
                "INSERT INTO audit_event(occurred_at,event_type,entity_type,entity_id,details_json) VALUES(?,?,?,?,?)",
                (
                    deleted_at,
                    "assessment_deleted",
                    "assessment",
                    str(assessment_id),
                    json.dumps(details, ensure_ascii=False, sort_keys=True),
                ),
            )
        if self.automatic_backups:
            self.create_local_backup(label=f"assessment_deleted_{assessment_id}")
        return deleted_at

    def create_attempt(self, assessment_id: int, student_id: int) -> int:
        """Crée la passation et copie les items figés dans la même transaction."""

        with self.transaction() as conn:
            assessment_rows = self.q("SELECT deleted_at,config_json FROM assessment WHERE id=?", (assessment_id,))
            if not self.q("SELECT id FROM student WHERE id=? AND deleted_at IS NULL", (student_id,)):
                raise ValueError("Élève introuvable ou retiré de la classe.")
            if not assessment_rows or assessment_rows[0]["deleted_at"] is not None:
                raise RuntimeError("Évaluation introuvable ou supprimée.")
            if not self.verify_assessment_integrity(assessment_id):
                raise RuntimeError("La vérification de l’empreinte de l’évaluation a échoué.")
            config = json.loads(assessment_rows[0]["config_json"] or "{}")
            protocol = config.get("familiarization_protocol", "numpad_copy_v1")
            trials = copy_trials(protocol) if config.get("familiarization_enabled", False) else ()
            cursor = conn.execute(
                "INSERT INTO attempt(attempt_uuid,assessment_id,student_id,started_at,software_version,ended_reason) "
                "VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), assessment_id, student_id, utc_now_iso(), SOFTWARE_VERSION, "in_progress"),
            )
            attempt_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO attempt_item(attempt_id,item_uuid,idx,position,op,a,b,expected,evaluated,kind,is_practice,is_anchor,fact_family,difficulty_category,fact_key) "
                "SELECT ?,item_uuid,idx,position,op,a,b,expected,evaluated,kind,is_practice,is_anchor,fact_family,difficulty_category,fact_key "
                "FROM assessment_item WHERE assessment_id=? ORDER BY position",
                (attempt_id, assessment_id),
            )
            conn.executemany(
                "INSERT INTO familiarization_trial(attempt_id,position,protocol,phase,target,initial_text) "
                "VALUES(?,?,?,?,?,?)",
                [(attempt_id, index, protocol, trial.phase, trial.target, trial.initial_text)
                 for index, trial in enumerate(trials)],
            )
        self.audit("attempt_started", "attempt", attempt_id, {"assessment_id": assessment_id, "student_id": student_id})
        return attempt_id

    def load_familiarization_trials(self, attempt_id: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.q(
            "SELECT * FROM familiarization_trial WHERE attempt_id=? ORDER BY position", (attempt_id,)
        )]

    def save_familiarization_response(
        self, trial_id: int, raw_text: str, timing: TimingResult, completion_status: str,
    ) -> None:
        """Enregistre les copies du pavé numérique séparément des calculs."""
        if completion_status not in {"answered", "omission", "timeout", "interrupted"}:
            raise ValueError("Statut de fin de familiarisation invalide.")
        with self.transaction() as conn:
            trial = conn.execute("SELECT * FROM familiarization_trial WHERE id=?", (trial_id,)).fetchone()
            if trial is None:
                raise ValueError("Essai de familiarisation introuvable.")
            if trial["response_json"] is not None:
                raise RuntimeError("Une réponse a déjà été enregistrée pour cet essai.")
            correct = (
                raw_text == trial["target"]
                and (trial["phase"] != "guided_correction" or timing.correction_count > 0)
            ) if completion_status == "answered" else None
            payload = {
                "raw_answer_text": raw_text, "is_correct": correct,
                "completion_status": completion_status,
                "presented_at": timing.presented_at, "first_key_at": timing.first_key_at,
                "validated_at": timing.validated_at,
                "reaction_time_first_key_ms": timing.reaction_time_first_key_ms,
                "typing_time_ms": timing.typing_time_ms,
                "total_response_time_ms": timing.total_response_time_ms,
                "keystroke_count": timing.keystroke_count, "correction_count": timing.correction_count,
                "events": timing.event_dicts(), "software_version": SOFTWARE_VERSION,
            }
            conn.execute(
                "UPDATE familiarization_trial SET response_json=?,record_hash=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False, sort_keys=True), _canonical_hash(payload), trial_id),
            )

    def load_attempt_items(self, attempt_id: int) -> list[sqlite3.Row]:
        return self.q(
            "SELECT id AS attempt_item_id,item_uuid,idx,position,op,a,b,expected,evaluated,kind,"
            "is_practice,is_anchor,fact_family,difficulty_category,fact_key "
            "FROM attempt_item WHERE attempt_id=? ORDER BY position",
            (attempt_id,),
        )

    def save_response(
        self,
        attempt_item_id: int,
        answer: int | None,
        correct: bool | None,
        raw_answer_text: str,
        timing: TimingResult,
        completion_status: str,
        timeout_status: str = "none",
    ) -> int:
        """Ajoute la réponse brute et la chronologie des touches acceptées."""

        if completion_status not in {"answered", "omission", "timeout", "interrupted", "global_timeout"}:
            raise ValueError("Statut de fin invalide.")
        if timeout_status not in {"none", "item", "global"}:
            raise ValueError("Statut d’expiration invalide.")
        if self.q("SELECT id FROM attempt_response WHERE attempt_item_id=?", (attempt_item_id,)):
            raise RuntimeError("Une réponse a déjà été enregistrée pour cet item.")
        event_dicts = timing.event_dicts()
        payload = {
            "attempt_item_id": attempt_item_id,
            "answer": answer,
            "correct": correct,
            "presented_at": timing.presented_at,
            "first_key_at": timing.first_key_at,
            "validated_at": timing.validated_at,
            "reaction_time_first_key_ms": timing.reaction_time_first_key_ms,
            "typing_time_ms": timing.typing_time_ms,
            "total_response_time_ms": timing.total_response_time_ms,
            "keystroke_count": timing.keystroke_count,
            "correction_count": timing.correction_count,
            "timeout_status": timeout_status,
            "completion_status": completion_status,
            "events": event_dicts,
            "software_version": SOFTWARE_VERSION,
        }
        record_hash = _canonical_hash(payload)
        response_columns = {str(row["name"]): int(row["notnull"]) for row in self.q("PRAGMA table_info(attempt_response)")}
        answer_value = 0 if answer is None and response_columns.get("answer", 0) else answer
        correct_value = 0 if correct is None and response_columns.get("correct", 0) else (None if correct is None else int(correct))
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO attempt_response(attempt_item_id,answer,correct,presented_at,first_key_at,validated_at,"
                "raw_answer_text,reaction_time_first_key_ms,typing_time_ms,total_response_time_ms,keystroke_count,"
                "correction_count,timeout_status,completion_status,event_json,software_version,record_hash,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    attempt_item_id, answer_value, correct_value, timing.presented_at, timing.first_key_at,
                    timing.validated_at, raw_answer_text, timing.reaction_time_first_key_ms,
                    timing.typing_time_ms, timing.total_response_time_ms, timing.keystroke_count,
                    timing.correction_count, timeout_status, completion_status,
                    json.dumps(event_dicts, ensure_ascii=False, separators=(",", ":")), SOFTWARE_VERSION,
                    record_hash, utc_now_iso(),
                ),
            )
            response_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT INTO response_key_event(response_id,event_index,event_type,key_value,elapsed_ms) VALUES(?,?,?,?,?)",
                [
                    (response_id, index, event["event"], event["value"], event["elapsed_ms"])
                    for index, event in enumerate(event_dicts)
                ],
            )
        return response_id

    def finish_attempt(self, attempt_id: int, ended_reason: str, duration_ms: float) -> None:
        """Distingue les items non présentés des réponses fausses."""

        rows = self.q(
            "SELECT ai.evaluated,ar.correct,ar.completion_status,ar.timeout_status,ar.record_hash "
            "FROM attempt_item ai LEFT JOIN attempt_response ar ON ar.attempt_item_id=ai.id "
            "WHERE ai.attempt_id=? ORDER BY ai.position",
            (attempt_id,),
        )
        scored = [row for row in rows if int(row["evaluated"] or 0) == 1]
        presented = [row for row in scored if row["completion_status"] is not None]
        answered = [row for row in presented if row["completion_status"] == "answered"]
        correct_count = sum(int(row["correct"] or 0) == 1 for row in answered)
        incorrect_count = len(answered) - correct_count
        timeout_count = sum(row["timeout_status"] in {"item", "global"} for row in presented)
        omission_count = sum(row["completion_status"] == "omission" for row in presented)
        not_presented = len(scored) - len(presented)
        percent = 100.0 * correct_count / len(answered) if answered else 0.0
        integrity_hash = _canonical_hash([row["record_hash"] for row in presented])
        self.exec(
            "UPDATE attempt SET finished_at=?,duration_s=?,duration_ms=?,max_score=?,score=?,percent=?,ended_reason=?,"
            "items_presented=?,items_answered=?,items_correct=?,items_incorrect=?,items_timeout=?,items_omitted=?,"
            "items_not_presented=?,integrity_hash=? WHERE id=?",
            (
                utc_now_iso(), int(round(duration_ms / 1000)), round(duration_ms, 3), len(scored), correct_count,
                percent, ended_reason, len(presented), len(answered), correct_count, incorrect_count,
                timeout_count, omission_count, not_presented, integrity_hash, attempt_id,
            ),
        )
        self.audit("attempt_finished", "attempt", attempt_id, {"ended_reason": ended_reason})
        if self.automatic_backups:
            self.create_local_backup(label=f"attempt_{attempt_id}")

    def assessment_items_payload(self, assessment_id: int) -> list[dict[str, Any]]:
        rows = self.q(
            "SELECT item_uuid,position,op,a,b,expected,evaluated,kind,is_practice,is_anchor,fact_family,"
            "difficulty_category,fact_key FROM assessment_item WHERE assessment_id=? ORDER BY position",
            (assessment_id,),
        )
        return [dict(row) for row in rows]

    def verify_assessment_integrity(self, assessment_id: int) -> bool:
        """Vérifie l’empreinte de la liste d’items figée."""

        rows = self.q("SELECT items_hash FROM assessment WHERE id=?", (assessment_id,))
        if not rows:
            return False
        expected = rows[0]["items_hash"]
        if not expected:
            # Les évaluations anciennes restent figées même sans empreinte.
            return True
        return secrets.compare_digest(str(expected), _canonical_hash(self.assessment_items_payload(assessment_id)))

    def create_local_backup(self, label: str = "manual") -> tuple[str, str | None]:
        """Sauvegarde ensemble les bases de résultats et d’identités."""

        if self.conn is None or self.path is None:
            raise RuntimeError("La base de données est fermée.")
        source = Path(self.path)
        backup_dir = source.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        main_path = backup_dir / f"{source.stem}_{label}_{stamp}.sqlite"
        target = sqlite3.connect(str(main_path))
        self.conn.backup(target, name="main")
        target.close()
        identity_backup: str | None = None
        if self.identity_path:
            identity_source = sqlite3.connect(self.identity_path)
            identity_target_path = backup_dir / f"{source.stem}_{label}_{stamp}.identities.sqlite"
            identity_target = sqlite3.connect(str(identity_target_path))
            identity_source.backup(identity_target)
            identity_source.close()
            identity_target.close()
            self._protect_identity_file(identity_target_path)
            identity_backup = str(identity_target_path)
        return str(main_path), identity_backup


DB = Database
canonical_hash = _canonical_hash
