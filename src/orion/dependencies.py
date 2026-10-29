"""Persistent DAG registration and read-only, evidence-based scheduling status."""
import sqlite3
from contextlib import nullcontext
from .models import ValidationError
from .service import Service, timestamp
from .events import append_event
from .workers import REGISTRY


class DependencyService:
    def __init__(self, database):
        self.database = database

    def add(self, task_id: str, prerequisite_id: str, *, connection=None) -> dict:
        with (self.database.connect(write=True) if connection is None else nullcontext(connection)) as c:
            service = Service(self.database)
            task = service._get(c, "tasks", task_id)
            prerequisite = service._get(c, "tasks", prerequisite_id)
            if task["status"] != "pending":
                raise ValidationError("Dependencies can only be registered for pending tasks")
            if task["id"] == prerequisite["id"]:
                raise ValidationError("Self-dependency is forbidden")
            if task["project_id"] != prerequisite["project_id"]:
                raise ValidationError("Dependencies must stay within one project")
            try:
                c.execute("INSERT INTO task_dependencies VALUES (?,?,?)", (task["id"], prerequisite["id"], timestamp()))
            except sqlite3.IntegrityError as exc:
                raise ValidationError("Invalid dependency (duplicate, cycle or constraint): " + str(exc)) from None
            append_event(c, "dependency_registered", task["id"], details={"prerequisite_id": prerequisite["id"]})
            return {"task_id": task["id"], "prerequisite_id": prerequisite["id"]}

    def evidence(self, c, task: dict) -> dict:
        result = {"task_id": task["id"], "satisfied": False, "execution_id": None, "verification_id": None}
        if task["status"] != "completed":
            return {**result, "reason": "Task state is " + task["status"]}
        execution = c.execute("SELECT * FROM executions WHERE task_id=? ORDER BY attempt DESC LIMIT 1", (task["id"],)).fetchone()
        if execution is None:
            return {**result, "reason": "No execution evidence; manual completion is insufficient"}
        result["execution_id"] = execution["id"]
        if execution["status"] != "succeeded":
            return {**result, "reason": "Latest execution is " + execution["status"]}
        worker = REGISTRY.get(execution["worker_id"])
        if worker is None:
            return {**result, "reason": "Unknown worker verification policy"}
        if worker.required_verifier:
            verification = c.execute("SELECT * FROM verifications WHERE execution_id=? ORDER BY rowid DESC LIMIT 1", (execution["id"],)).fetchone()
            binding_table = "synthesis_runs" if execution["worker_id"] == "research-synthesize" else "research_runs" if execution["worker_id"] == "research-collect" else "execution_inputs"
            binding = c.execute(f"SELECT * FROM {binding_table} WHERE execution_id=?", (execution["id"],)).fetchone()
            if verification is None:
                return {**result, "reason": "Required verification is missing"}
            result["verification_id"] = verification["id"]
            if verification["status"] != "passed" or verification["verifier"] != worker.required_verifier:
                return {**result, "reason": "Latest verification failed or has the wrong verifier"}
            if binding is None or verification["input_digest"] != binding["sha256"] or not verification["artifact_digest"] or verification["artifact_digest"] != binding["artifact_digest"]:
                return {**result, "reason": "Verification digests do not match execution binding"}
        return {**result, "satisfied": True, "reason": "Latest execution satisfies required evidence"}

    def project(self, project_id: str, *, connection=None) -> dict:
        with (self.database.connect() if connection is None else nullcontext(connection)) as c:
            if connection is None: c.execute("BEGIN")
            project = Service(self.database)._get(c, "projects", project_id)
            rows = c.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY priority DESC,created_at,id LIMIT 10001", (project["id"],)).fetchall()
            if len(rows)>10000: raise ValidationError("Queue inspection supports at most 10000 tasks per project")
            tasks = {row["id"]: dict(row) for row in rows}
            edges = [dict(row) for row in c.execute("SELECT d.* FROM task_dependencies d JOIN tasks t ON t.id=d.task_id WHERE t.project_id=? ORDER BY d.task_id,d.prerequisite_id", (project["id"],))]
            parents = {key: [] for key in tasks}
            for edge in edges: parents[edge["task_id"]].append(edge["prerequisite_id"])
            # Iterative topological evaluation avoids recursion depth limits.
            remaining = set(tasks); evaluated = {}
            while remaining:
                candidates = sorted(key for key in remaining if all(p in evaluated for p in parents[key]))
                if not candidates: raise ValidationError("Inconsistent dependency graph: cycle or missing/cross-project prerequisite")
                for key in candidates:
                    task = tasks[key]; own = self.evidence(c, task)
                    prerequisites = [{"task_id":p, "classification":evaluated[p]["classification"], "satisfied":evaluated[p]["classification"]=="completed", "reason":evaluated[p]["reason"], "execution_id":evaluated[p]["evidence"]["execution_id"], "verification_id":evaluated[p]["evidence"]["verification_id"]} for p in parents[key]]
                    bad = [p for p in prerequisites if not p["satisfied"]]
                    if task["status"] in ("failed","cancelled","blocked"):
                        classification, reason = "blocked", "Task state is " + task["status"]
                    elif any(p["classification"]=="blocked" for p in bad):
                        classification, reason = "blocked", "A prerequisite is blocked or lacks valid success evidence"
                    elif bad:
                        classification, reason = "waiting", "Prerequisites are not yet complete"
                    elif task["status"]=="completed":
                        classification, reason = ("completed" if own["satisfied"] else "blocked"), own["reason"]
                    elif task["status"]=="in_progress":
                        classification, reason = "waiting", "Task is in progress; inspect execution/recovery history"
                    else:
                        classification, reason = "ready", "Prerequisites satisfied; execution approval and global slot still apply"
                    evaluated[key] = {"task_id":key,"title":task["title"],"task_status":task["status"],"priority":task["priority"],"classification":classification,"reason":reason,"prerequisites":prerequisites,"evidence":own,
                        "approval_required":bool(c.execute("SELECT 1 FROM approval_policy WHERE task_id=?",(key,)).fetchone())}
                    remaining.remove(key)
            return {"project_id":project["id"], "tasks":[evaluated[key] for key in tasks], "dependencies":edges}

    def explain(self, task_id: str, *, connection=None) -> dict:
        with (self.database.connect() if connection is None else nullcontext(connection)) as c:
            if connection is None: c.execute("BEGIN")
            task = Service(self.database)._get(c,"tasks",task_id)
            return next(row for row in self.project(task["project_id"],connection=c)["tasks"] if row["task_id"]==task["id"])

    def enforce(self, c, task_id: str) -> None:
        explanation = self.explain(task_id,connection=c)
        if explanation["classification"] != "ready":
            append_event(c,"execution_rejected_dependencies",explanation["task_id"],details={"reason":explanation["reason"],"prerequisites":explanation["prerequisites"]})
            c.commit()  # Preserve rejection audit; no execution claim has been created.
            raise ValidationError("Dependencies unsatisfied: " + explanation["reason"] + "; inspect queue explain " + task_id)
