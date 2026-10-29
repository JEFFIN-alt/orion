"""Durable single-use approval gates, checked within the execution claim transaction."""
import hashlib
import json
from uuid import uuid4
from .events import append_event
from .models import ValidationError, NotFoundError, required
from .service import Service, identifier, timestamp
from .workers import resolve


def proposal(c, database, task_id, worker_id, worker, timeout=10):
    task = Service(database)._get(c, "tasks", task_id)
    project = Service(database)._get(c, "projects", task["project_id"])
    rows = c.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY created_at,id LIMIT 10001", (project["id"],)).fetchall()
    if len(rows) > 10000:
        raise ValidationError("Report limit is 10000 tasks")
    data = {"task_id": task["id"], "worker_id": worker_id, "worker": worker.describe(),
            "timeout": float(timeout), "data_directory": str(database.path.resolve().parent),
            "project": project, "tasks": [dict(row) for row in rows]}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(encoded) > 8_000_000:
        raise ValidationError("Report snapshot exceeds 8 MB limit")
    return data, hashlib.sha256(encoded.encode()).hexdigest()


def authorize(c, database, task_id, worker_id, worker, timeout):
    if not c.execute("SELECT 1 FROM approval_policy WHERE task_id=?", (task_id,)).fetchone():
        return None
    _, fingerprint = proposal(c, database, task_id, worker_id, worker, timeout)
    rows = c.execute("SELECT * FROM approvals WHERE task_id=? AND status='approved' AND execution_id IS NULL ORDER BY created_at DESC", (task_id,)).fetchall()
    for row in rows:
        if row["worker_id"] == worker_id and row["fingerprint"] == fingerprint:
            return row["id"]
    if rows:
        append_event(c, "approval_invalidated", task_id, details={"approval_ids": [row["id"] for row in rows]})
    append_event(c, "execution_rejected_approval", task_id, details={"worker_id": worker_id, "reason": "missing, undecided, rejected, consumed or stale approval"})
    # Persist rejection audit even though the caller's claim will be aborted.
    c.commit()
    raise ValidationError("A current, unused approved request is required for this exact operation")


class ApprovalService:
    def __init__(self, database):
        self.database = database

    def require(self, task_id):
        with self.database.connect(write=True) as c:
            task = Service(self.database)._get(c, "tasks", task_id)
            if c.execute("SELECT 1 FROM executions WHERE task_id=? AND status='running'", (task["id"],)).fetchone():
                raise ValidationError("Cannot change approval policy during execution")
            c.execute("INSERT OR IGNORE INTO approval_policy VALUES (?,?)", (task["id"], timestamp()))
            append_event(c, "approval_required", task["id"])
        return {"task_id": task["id"], "approval_required": True}

    def request(self, task_id, worker_id, reason):
        reason = required(reason, "reason")
        worker = resolve(worker_id)
        with self.database.connect(write=True) as c:
            task = Service(self.database)._get(c, "tasks", task_id)
            if task["status"] != "pending":
                raise ValidationError("Approval requests require a pending task")
            data, fingerprint = proposal(c, self.database, task["id"], worker_id, worker)
            c.execute("INSERT OR IGNORE INTO approval_policy VALUES (?,?)", (task["id"], timestamp()))
            approval_id = str(uuid4())
            c.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (approval_id, task["id"], worker_id, "Generate project status report", fingerprint, json.dumps(data), reason, timestamp(), "pending", None, None, None))
            append_event(c, "approval_requested", task["id"], details={"approval_id": approval_id, "fingerprint": fingerprint})
        return self.get(approval_id)

    def get(self, approval_id):
        with self.database.connect() as c:
            row = c.execute("SELECT * FROM approvals WHERE id=?", (identifier(approval_id),)).fetchone()
            if row is None:
                raise NotFoundError("Approval not found")
            return dict(row)

    def pending(self):
        with self.database.connect() as c:
            return [dict(row) for row in c.execute("SELECT * FROM approvals WHERE status='pending' ORDER BY created_at")]

    def decide(self, approval_id, decision, explanation):
        if decision not in ("approved", "rejected"):
            raise ValidationError("Decision must be approved or rejected")
        explanation = required(explanation, "explanation")
        with self.database.connect(write=True) as c:
            row = c.execute("SELECT * FROM approvals WHERE id=?", (identifier(approval_id),)).fetchone()
            if row is None or row["status"] != "pending":
                raise ValidationError("Approval does not exist or already has a decision")
            c.execute("UPDATE approvals SET status=?, decided_at=?, explanation=? WHERE id=?", (decision, timestamp(), explanation, row["id"]))
            append_event(c, "approval_granted" if decision == "approved" else "approval_rejected", row["task_id"], details={"approval_id": row["id"]})
        return self.get(approval_id)
