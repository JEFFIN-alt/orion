"""Transactional project/task operations; SQL is kept here to avoid pass-through layers."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .database import Database
from .models import NotFoundError, ValidationError, PROJECT_TRANSITIONS, TASK_TRANSITIONS, required


def identifier(value: str) -> str:
    value = required(value, "identifier")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValidationError("identifier must be a UUID") from exc


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Service:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def table(kind: str) -> str:
        if kind not in ("projects", "tasks"):
            raise ValidationError("kind must be projects or tasks")
        return kind

    def _get(self, connection, kind: str, record_id: str) -> dict:
        row = connection.execute(f"SELECT * FROM {self.table(kind)} WHERE id=?", (identifier(record_id),)).fetchone()
        if row is None:
            raise NotFoundError(f"{kind}: {record_id} not found")
        return dict(row)

    def get(self, kind: str, record_id: str) -> dict:
        with self.database.connect() as connection:
            return self._get(connection, kind, record_id)

    def list(self, kind: str, project_id: str | None = None) -> list[dict]:
        table = self.table(kind)
        with self.database.connect() as connection:
            if project_id is not None:
                if kind != "tasks":
                    raise ValidationError("project filter only applies to tasks")
                project_id = identifier(project_id)
                self._get(connection, "projects", project_id)
                rows = connection.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY priority DESC, created_at, id", (project_id,))
            else:
                rows = connection.execute(f"SELECT * FROM {table} ORDER BY created_at, id")
            return [dict(row) for row in rows]

    @staticmethod
    def validate_fields(kind: str, fields: dict) -> dict:
        allowed = {"name", "description"} if kind == "projects" else {"title", "description", "priority", "summary"}
        if not fields or fields.keys() - allowed:
            raise ValidationError("No fields supplied or unsupported fields")
        result = dict(fields)
        for key, value in result.items():
            if key in ("title", "name"):
                result[key] = required(value, key)
            elif key == "priority":
                if type(value) is not int or not 0 <= value <= 100:
                    raise ValidationError("priority must be an integer from 0 to 100")
            elif not isinstance(value, str) and not (key == "summary" and value is None):
                raise ValidationError(f"{key} must be text")
        return result

    def create_project(self, name: str, description: str = "") -> dict:
        values = self.validate_fields("projects", {"name": name, "description": description})
        now, record_id = timestamp(), str(uuid4())
        with self.database.connect(write=True) as connection:
            connection.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)", (record_id, values["name"], description, "active", now, now))
            return self._get(connection, "projects", record_id)

    def create_task(self, project_id: str, title: str, description: str = "", priority: int = 0, require_approval: bool = False) -> dict:
        values = self.validate_fields("tasks", {"title": title, "description": description, "priority": priority})
        now, record_id = timestamp(), str(uuid4())
        with self.database.connect(write=True) as connection:
            project = self._get(connection, "projects", project_id)
            connection.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", (record_id, project["id"], values["title"], description, "pending", priority, now, now, None))
            if require_approval:
                connection.execute("INSERT INTO approval_policy VALUES (?,?)", (record_id, now))
                from .events import append_event
                append_event(connection, "approval_required", record_id)
            return self._get(connection, "tasks", record_id)

    def update(self, kind: str, record_id: str, **fields) -> dict:
        table = self.table(kind)
        fields = self.validate_fields(kind, fields)
        with self.database.connect(write=True) as connection:
            self._get(connection, kind, record_id)
            fields["updated_at"] = timestamp()
            assignments = ", ".join(f"{key}=?" for key in fields)
            connection.execute(f"UPDATE {table} SET {assignments} WHERE id=?", (*fields.values(), identifier(record_id)))
            return self._get(connection, kind, record_id)

    def transition(self, kind: str, record_id: str, status: str, summary: str | None = None) -> dict:
        table = self.table(kind)
        if summary is not None and (kind != "tasks" or not isinstance(summary, str)):
            raise ValidationError("summary must be task text")
        with self.database.connect(write=True) as connection:
            current = self._get(connection, kind, record_id)
            if kind == "tasks" and connection.execute("SELECT 1 FROM executions WHERE task_id=? AND status='running'", (current["id"],)).fetchone():
                raise ValidationError("Cannot transition a task with an active execution")
            rules = TASK_TRANSITIONS if kind == "tasks" else PROJECT_TRANSITIONS
            if status not in rules[current["status"]]:
                raise ValidationError(f"Invalid transition: {current['status']} -> {status}")
            connection.execute(f"UPDATE {table} SET status=?, updated_at=? WHERE id=?", (status, timestamp(), current["id"]))
            if kind == "tasks" and status == "blocked":
                from .events import append_event
                append_event(connection, "task_blocked", current["id"])
            if summary is not None:
                connection.execute("UPDATE tasks SET summary=? WHERE id=?", (summary, current["id"]))
            return self._get(connection, kind, record_id)
