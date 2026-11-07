"""Schéma SQLite et protections utilisées par les migrations."""

# L’ancien schéma appelait une expiration « time_limit ».
ELIGIBLE_ATTEMPT_SQL = (
    "att.finished_at IS NOT NULL AND att.ended_reason IN ('completed','global_time_limit','time_limit')"
)

CORE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS student (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  last_name TEXT NOT NULL DEFAULT '',
  first_name TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  export_id TEXT,
  group_id TEXT NOT NULL DEFAULT 'classe',
  FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assessment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_uuid TEXT,
  project_id INTEGER NOT NULL,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  config_json TEXT NOT NULL,
  assessment_version TEXT NOT NULL DEFAULT '1',
  assessment_date TEXT,
  academic_period TEXT NOT NULL DEFAULT '',
  group_id TEXT NOT NULL DEFAULT 'classe',
  random_seed INTEGER,
  software_version TEXT,
  created_at TEXT,
  frozen_at TEXT,
  items_hash TEXT,
  deleted_at TEXT,
  deletion_reason TEXT,
  FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assessment_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL,
  item_uuid TEXT,
  idx INTEGER NOT NULL,
  position INTEGER,
  op TEXT NOT NULL DEFAULT 'multiplication',
  a INTEGER NOT NULL,
  b INTEGER NOT NULL DEFAULT 0,
  expected INTEGER NOT NULL,
  evaluated INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'scored',
  is_practice INTEGER NOT NULL DEFAULT 0,
  is_anchor INTEGER NOT NULL DEFAULT 0,
  fact_family TEXT NOT NULL DEFAULT '',
  difficulty_category TEXT NOT NULL DEFAULT '',
  fact_key TEXT NOT NULL DEFAULT '',
  UNIQUE(assessment_id, idx),
  FOREIGN KEY(assessment_id) REFERENCES assessment(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assessment_roster (
  assessment_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL,
  PRIMARY KEY(assessment_id, student_id),
  FOREIGN KEY(assessment_id) REFERENCES assessment(id) ON DELETE CASCADE,
  FOREIGN KEY(student_id) REFERENCES student(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attempt (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_uuid TEXT,
  assessment_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  duration_s INTEGER,
  duration_ms REAL,
  max_score INTEGER,
  score INTEGER,
  percent REAL,
  ended_reason TEXT,
  items_presented INTEGER NOT NULL DEFAULT 0,
  items_answered INTEGER NOT NULL DEFAULT 0,
  items_correct INTEGER NOT NULL DEFAULT 0,
  items_incorrect INTEGER NOT NULL DEFAULT 0,
  items_timeout INTEGER NOT NULL DEFAULT 0,
  items_omitted INTEGER NOT NULL DEFAULT 0,
  items_not_presented INTEGER NOT NULL DEFAULT 0,
  software_version TEXT,
  integrity_hash TEXT,
  FOREIGN KEY(assessment_id) REFERENCES assessment(id) ON DELETE CASCADE,
  FOREIGN KEY(student_id) REFERENCES student(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attempt_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id INTEGER NOT NULL,
  item_uuid TEXT,
  idx INTEGER NOT NULL,
  position INTEGER,
  op TEXT NOT NULL DEFAULT 'multiplication',
  a INTEGER NOT NULL,
  b INTEGER NOT NULL DEFAULT 0,
  expected INTEGER NOT NULL,
  evaluated INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'scored',
  is_practice INTEGER NOT NULL DEFAULT 0,
  is_anchor INTEGER NOT NULL DEFAULT 0,
  fact_family TEXT NOT NULL DEFAULT '',
  difficulty_category TEXT NOT NULL DEFAULT '',
  fact_key TEXT NOT NULL DEFAULT '',
  UNIQUE(attempt_id, idx),
  FOREIGN KEY(attempt_id) REFERENCES attempt(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attempt_response (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_item_id INTEGER NOT NULL,
  answer INTEGER,
  correct INTEGER,
  presented_at TEXT,
  first_key_at TEXT,
  validated_at TEXT,
  raw_answer_text TEXT,
  reaction_time_first_key_ms REAL,
  typing_time_ms REAL,
  total_response_time_ms REAL,
  keystroke_count INTEGER NOT NULL DEFAULT 0,
  correction_count INTEGER NOT NULL DEFAULT 0,
  timeout_status TEXT NOT NULL DEFAULT 'none',
  completion_status TEXT NOT NULL DEFAULT 'answered',
  event_json TEXT NOT NULL DEFAULT '[]',
  software_version TEXT,
  record_hash TEXT,
  created_at TEXT,
  FOREIGN KEY(attempt_item_id) REFERENCES attempt_item(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS response_key_event (
  response_id INTEGER NOT NULL,
  event_index INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  key_value TEXT NOT NULL DEFAULT '',
  elapsed_ms REAL NOT NULL,
  PRIMARY KEY(response_id, event_index),
  FOREIGN KEY(response_id) REFERENCES attempt_response(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS familiarization_trial (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id INTEGER NOT NULL REFERENCES attempt(id) ON DELETE RESTRICT,
  position INTEGER NOT NULL,
  protocol TEXT NOT NULL,
  phase TEXT NOT NULL,
  target TEXT NOT NULL,
  initial_text TEXT NOT NULL DEFAULT '',
  response_json TEXT,
  record_hash TEXT,
  UNIQUE(attempt_id, position)
);

CREATE TRIGGER IF NOT EXISTS prevent_familiarization_trial_change
BEFORE UPDATE OF attempt_id,position,protocol,phase,target,initial_text ON familiarization_trial
BEGIN SELECT RAISE(ABORT, 'familiarization protocol is frozen'); END;

CREATE TRIGGER IF NOT EXISTS prevent_familiarization_response_change
BEFORE UPDATE OF response_json,record_hash ON familiarization_trial
WHEN OLD.response_json IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'familiarization responses are immutable'); END;

CREATE TRIGGER IF NOT EXISTS prevent_familiarization_delete
BEFORE DELETE ON familiarization_trial
BEGIN SELECT RAISE(ABORT, 'familiarization trials are immutable'); END;

CREATE INDEX IF NOT EXISTS idx_student_project ON student(project_id);
CREATE INDEX IF NOT EXISTS idx_assessment_project ON assessment(project_id);
CREATE INDEX IF NOT EXISTS idx_assessment_item_assessment ON assessment_item(assessment_id);
CREATE INDEX IF NOT EXISTS idx_attempt_assessment ON attempt(assessment_id);
CREATE INDEX IF NOT EXISTS idx_attempt_student ON attempt(student_id);
CREATE INDEX IF NOT EXISTS idx_attempt_item_attempt ON attempt_item(attempt_id);
CREATE INDEX IF NOT EXISTS idx_response_attempt_item ON attempt_response(attempt_item_id);
"""


IDENTITY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS identity.student_identity (
  student_id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  last_name TEXT NOT NULL,
  first_name TEXT NOT NULL,
  internal_export_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
"""


IMMUTABILITY_TRIGGERS = {
    "prevent_frozen_item_insert": """
BEFORE INSERT ON assessment_item
WHEN (SELECT frozen_at FROM assessment WHERE id = NEW.assessment_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'assessment items are frozen'); END;""",

    "prevent_frozen_item_update": """
BEFORE UPDATE ON assessment_item
WHEN (SELECT frozen_at FROM assessment WHERE id = OLD.assessment_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'assessment items are frozen'); END;""",

    "prevent_frozen_item_delete": """
BEFORE DELETE ON assessment_item
WHEN (SELECT frozen_at FROM assessment WHERE id = OLD.assessment_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'assessment items are frozen'); END;""",

    "prevent_frozen_assessment_configuration_update": """
BEFORE UPDATE OF title, type, config_json, assessment_version, assessment_date, academic_period,
  group_id, random_seed, items_hash ON assessment
WHEN OLD.frozen_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'assessment configuration is frozen'); END;""",

    "prevent_started_assessment_thaw": """
BEFORE UPDATE OF frozen_at ON assessment
WHEN EXISTS (SELECT 1 FROM attempt WHERE assessment_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'started assessment is locked'); END;""",

    "prevent_response_update": """
BEFORE UPDATE ON attempt_response
BEGIN SELECT RAISE(ABORT, 'raw responses are immutable'); END;""",

    "prevent_response_delete": """
BEFORE DELETE ON attempt_response
BEGIN SELECT RAISE(ABORT, 'raw responses are immutable'); END;""",
}

# Compatibilité avec les imports de l’ancienne constante.
SCHEMA_SQL = CORE_SCHEMA_SQL
