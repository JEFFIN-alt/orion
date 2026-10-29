import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = (
    """CREATE TABLE projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name)) > 0),
        description TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','paused','completed','cancelled')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE tasks (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
        title TEXT NOT NULL CHECK(length(trim(title)) > 0), description TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','in_progress','blocked','completed','failed','cancelled')),
        priority INTEGER NOT NULL CHECK(typeof(priority) = 'integer' AND priority BETWEEN 0 AND 100),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, summary TEXT)""",
    "CREATE INDEX tasks_project_idx ON tasks(project_id)",
)


MIGRATION_2 = (
    """CREATE TABLE executions (
      id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), worker_id TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed')),
      started_at TEXT NOT NULL, finished_at TEXT, attempt INTEGER NOT NULL CHECK(attempt > 0),
      summary TEXT, result_json TEXT, error TEXT,
      UNIQUE(task_id, attempt),
      CHECK((status='running' AND finished_at IS NULL) OR (status!='running' AND finished_at IS NOT NULL)))""",
    "CREATE UNIQUE INDEX one_running_execution ON executions((1)) WHERE status='running'",
    """CREATE TABLE events (id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, type TEXT NOT NULL,
      task_id TEXT NOT NULL REFERENCES tasks(id), execution_id TEXT REFERENCES executions(id), details_json TEXT NOT NULL)""",
    "CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END",
    "CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END",
)


MIGRATION_3 = (
    "CREATE TABLE approval_policy (task_id TEXT PRIMARY KEY REFERENCES tasks(id), required_at TEXT NOT NULL)",
    """CREATE TABLE approvals (
      id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), worker_id TEXT NOT NULL,
      operation TEXT NOT NULL, fingerprint TEXT NOT NULL, proposal_json TEXT NOT NULL, reason TEXT NOT NULL,
      created_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
      decided_at TEXT, explanation TEXT, execution_id TEXT UNIQUE REFERENCES executions(id),
      CHECK((status='pending' AND decided_at IS NULL) OR (status!='pending' AND decided_at IS NOT NULL)))""",
    """CREATE TRIGGER approval_decision_immutable BEFORE UPDATE ON approvals
      WHEN OLD.status != 'pending' AND (NEW.status != OLD.status OR NEW.explanation IS NOT OLD.explanation OR NEW.decided_at IS NOT OLD.decided_at)
      BEGIN SELECT RAISE(ABORT, 'approval decision is immutable'); END""",
    """CREATE TABLE execution_ownership (
      execution_id TEXT PRIMARY KEY REFERENCES executions(id), host TEXT NOT NULL,
      parent_pid INTEGER NOT NULL, child_pid INTEGER,
      phase TEXT NOT NULL CHECK(phase IN ('not_started','starting','running','stopped')),
      recorded_at TEXT NOT NULL)""",
    """CREATE TABLE recoveries (execution_id TEXT PRIMARY KEY REFERENCES executions(id),
      decided_at TEXT NOT NULL, reason TEXT NOT NULL, evidence_json TEXT NOT NULL)""",
)


MIGRATION_4 = (
    """CREATE TABLE inputs (id TEXT PRIMARY KEY, filename TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
      sha256 TEXT NOT NULL, size INTEGER NOT NULL CHECK(size>=0), imported_at TEXT NOT NULL)""",
    """CREATE TABLE csv_operations (task_id TEXT PRIMARY KEY REFERENCES tasks(id),
      input_id TEXT NOT NULL REFERENCES inputs(id), limits_json TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE execution_inputs (execution_id TEXT PRIMARY KEY REFERENCES executions(id),
      input_id TEXT NOT NULL REFERENCES inputs(id), sha256 TEXT NOT NULL, limits_json TEXT NOT NULL, worker_version TEXT NOT NULL, artifact_digest TEXT)""",
    """CREATE TABLE verifications (id TEXT PRIMARY KEY, execution_id TEXT NOT NULL REFERENCES executions(id),
      verifier TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('passed','failed')),
      input_digest TEXT, artifact_digest TEXT, verified_at TEXT NOT NULL, checks_json TEXT NOT NULL, summary TEXT NOT NULL)""",
    "CREATE TRIGGER verifications_no_update BEFORE UPDATE ON verifications BEGIN SELECT RAISE(ABORT, 'verification history is immutable'); END",
    "CREATE TRIGGER verifications_no_delete BEFORE DELETE ON verifications BEGIN SELECT RAISE(ABORT, 'verification history is immutable'); END",
)


MIGRATION_5 = (
    """CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL,
      project_id TEXT REFERENCES projects(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
      role TEXT NOT NULL CHECK(role IN ('user','assistant','system')), kind TEXT NOT NULL CHECK(kind IN ('user','model','status','error')),
      content TEXT NOT NULL, provider TEXT, model TEXT, elapsed_seconds REAL, created_at TEXT NOT NULL)""",
    "CREATE INDEX conversation_messages ON messages(conversation_id,created_at)",
    """CREATE TABLE plans (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
      message_id TEXT NOT NULL UNIQUE REFERENCES messages(id), body_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('proposed','approved','rejected')), created_at TEXT NOT NULL,
      decided_at TEXT, reason TEXT, project_id TEXT REFERENCES projects(id), task_ids_json TEXT)""",
    """CREATE TRIGGER plans_content_immutable BEFORE UPDATE ON plans
      WHEN NEW.body_json != OLD.body_json OR NEW.fingerprint != OLD.fingerprint OR (OLD.status!='proposed' AND NEW.status!=OLD.status)
      BEGIN SELECT RAISE(ABORT,'Plan content and decisions cannot be rewritten'); END""",
    """CREATE TABLE chat_events (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
      plan_id TEXT REFERENCES plans(id), event_type TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL)""",
    "CREATE TRIGGER chat_events_no_update BEFORE UPDATE ON chat_events BEGIN SELECT RAISE(ABORT,'Chat events are append-only'); END",
    "CREATE TRIGGER chat_events_no_delete BEFORE DELETE ON chat_events BEGIN SELECT RAISE(ABORT,'Chat events are append-only'); END",
    """CREATE TABLE inference_claim (slot INTEGER PRIMARY KEY CHECK(slot=1), token TEXT NOT NULL,
      owner_pid INTEGER NOT NULL, started_at TEXT NOT NULL, uncertain INTEGER NOT NULL DEFAULT 0)""",
)


MIGRATION_6 = (
    """CREATE TABLE task_dependencies (task_id TEXT NOT NULL REFERENCES tasks(id),
      prerequisite_id TEXT NOT NULL REFERENCES tasks(id), created_at TEXT NOT NULL,
      PRIMARY KEY(task_id,prerequisite_id), CHECK(task_id!=prerequisite_id))""",
    "CREATE INDEX dependency_prerequisite ON task_dependencies(prerequisite_id)",
    """CREATE TRIGGER dependencies_validate BEFORE INSERT ON task_dependencies BEGIN
      SELECT CASE WHEN (SELECT project_id FROM tasks WHERE id=NEW.task_id) !=
        (SELECT project_id FROM tasks WHERE id=NEW.prerequisite_id) THEN RAISE(ABORT,'Cross-project dependency') END;
      SELECT CASE WHEN EXISTS(WITH RECURSIVE ancestors(id) AS (
        SELECT NEW.prerequisite_id UNION SELECT d.prerequisite_id FROM task_dependencies d JOIN ancestors a ON d.task_id=a.id)
        SELECT 1 FROM ancestors WHERE id=NEW.task_id) THEN RAISE(ABORT,'Dependency cycle') END;
      END""",
    "CREATE TRIGGER dependencies_no_update BEFORE UPDATE ON task_dependencies BEGIN SELECT RAISE(ABORT,'Dependencies cannot be rewritten'); END",
)


MIGRATION_7 = (
    "CREATE TABLE research_operations (task_id TEXT PRIMARY KEY REFERENCES tasks(id), operation_id TEXT NOT NULL UNIQUE, config_json TEXT NOT NULL, configured_at TEXT NOT NULL)",
    "CREATE TABLE research_runs (execution_id TEXT PRIMARY KEY REFERENCES executions(id), operation_json TEXT NOT NULL, sha256 TEXT NOT NULL, artifact_digest TEXT)",
    "CREATE TABLE research_captures (execution_id TEXT PRIMARY KEY REFERENCES executions(id), captures_json TEXT NOT NULL, sha256 TEXT NOT NULL)",
    "CREATE TRIGGER research_runs_binding BEFORE UPDATE ON research_runs WHEN NEW.execution_id!=OLD.execution_id OR NEW.operation_json!=OLD.operation_json OR NEW.sha256!=OLD.sha256 OR OLD.artifact_digest IS NOT NULL BEGIN SELECT RAISE(ABORT,'Research binding is immutable'); END",
    "CREATE TRIGGER research_runs_no_delete BEFORE DELETE ON research_runs BEGIN SELECT RAISE(ABORT,'Research binding is immutable'); END",
    "CREATE TRIGGER research_captures_no_update BEFORE UPDATE ON research_captures BEGIN SELECT RAISE(ABORT,'Research captures are immutable'); END",
    "CREATE TRIGGER research_captures_no_delete BEFORE DELETE ON research_captures BEGIN SELECT RAISE(ABORT,'Research captures are immutable'); END",
)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect(write=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4, 5, 6, 7):
                raise RuntimeError(f"Unsupported database schema version: {version}")
            if version == 0:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 1")
            if version < 2:
                for statement in MIGRATION_2:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 2")
            if version < 3:
                for statement in MIGRATION_3:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 3")
            if version < 4:
                for statement in MIGRATION_4:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 4")
            if version < 5:
                for statement in MIGRATION_5:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 5")
            if version < 6:
                for statement in MIGRATION_6:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 6")

            if version < 7:
                for statement in MIGRATION_7:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 7")

    def health(self) -> dict:
        with self.connect() as connection:
            return {"schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
                    "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "foreign_key_errors": [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]}
