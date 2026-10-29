"""Conservative local process evidence; no heartbeat assumptions or automatic retries."""
import ctypes
import json
import os
import socket
from .events import append_event
from .models import ValidationError, NotFoundError, required
from .service import identifier, timestamp


def process_state(pid):
    if not isinstance(pid, int) or pid <= 0:
        return "unknown"
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            return "stopped" if ctypes.get_last_error() == 87 else "unknown"
        try:
            result = kernel.WaitForSingleObject(handle, 0)
            return "stopped" if result == 0 else "active" if result == 258 else "unknown"
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return "active"
    except ProcessLookupError:
        return "stopped"
    except OSError:
        return "unknown"


class RecoveryService:
    def __init__(self, database):
        self.database = database

    def _inspect(self, c, execution_id):
        row = c.execute("SELECT * FROM executions WHERE id=?", (identifier(execution_id),)).fetchone()
        if row is None:
            raise NotFoundError("Execution not found")
        owner = c.execute("SELECT * FROM execution_ownership WHERE execution_id=?", (row["id"],)).fetchone()
        evidence = {"execution_id": row["id"], "task_id": row["task_id"], "status": row["status"], "ownership": dict(owner) if owner else None, "safe_to_recover": False}
        if row["status"] != "running":
            evidence["reason"] = "Already terminal; history must remain unchanged"
        elif owner is None or owner["host"] != socket.gethostname():
            evidence["reason"] = "Unknown or nonlocal ownership; operator investigation required"
        else:
            parent = process_state(owner["parent_pid"])
            child = "stopped" if owner["phase"] in ("not_started", "stopped") else process_state(owner["child_pid"]) if owner["phase"] == "running" else "unknown"
            evidence.update(parent_state=parent, child_state=child)
            evidence["safe_to_recover"] = parent == "stopped" and child == "stopped"
            evidence["reason"] = "Both processes proven stopped (or child never launched)" if evidence["safe_to_recover"] else "Parent/child is active or evidence is ambiguous; leave unresolved"
        evidence["artifact_exists"] = (self.database.path.resolve().parent / "artifacts" / f"{row['id']}.json").exists()
        return evidence

    def inspect(self, execution_id):
        with self.database.connect(write=True) as c:
            evidence = self._inspect(c, execution_id)
            append_event(c, "recovery_inspection", evidence["task_id"], evidence["execution_id"], {"safe_to_recover": evidence["safe_to_recover"]})
            if evidence["safe_to_recover"]:
                append_event(c, "interrupted_execution_detected", evidence["task_id"], evidence["execution_id"])
            return evidence

    def running(self):
        with self.database.connect() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM executions WHERE status='running'")]
        return [self.inspect(i) for i in ids]

    def confirm(self, execution_id, reason):
        reason = required(reason, "reason")
        refused = False
        with self.database.connect(write=True) as c:
            evidence = self._inspect(c, execution_id)
            if not evidence["safe_to_recover"]:
                append_event(c, "recovery_refused", evidence["task_id"], evidence["execution_id"], {"reason": evidence["reason"]})
                refused = True
            else:
                now = timestamp()
                c.execute("INSERT INTO recoveries VALUES (?,?,?,?)", (evidence["execution_id"], now, reason, json.dumps(evidence)))
                c.execute("UPDATE executions SET status='failed', finished_at=?, summary='Interrupted execution confirmed by operator', error='Interrupted: outcome unknown; do not infer success from artifacts' WHERE id=? AND status='running'", (now, evidence["execution_id"]))
                c.execute("UPDATE tasks SET status='blocked', updated_at=?, summary='Recovery confirmed; review partial effects before requeue' WHERE id=?", (now, evidence["task_id"]))
                append_event(c, "recovery_authorized", evidence["task_id"], evidence["execution_id"])
                append_event(c, "task_blocked", evidence["task_id"], evidence["execution_id"])
        if refused:
            raise ValidationError(evidence["reason"])
        return {"execution_id": evidence["execution_id"], "recovered": True, "task_status": "blocked", "reason": reason}
