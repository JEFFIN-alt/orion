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
            if version not in (0, 1, 2, 3):
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

    def health(self) -> dict:
        with self.connect() as connection:
            return {"schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
                    "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "foreign_key_errors": [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]}
