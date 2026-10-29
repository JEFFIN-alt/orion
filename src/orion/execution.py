"""One-shot execution with a persistent exclusive claim and bounded child process."""
import hashlib
import os
import socket
import json
import multiprocessing
import traceback
from pathlib import Path
from uuid import uuid4

from .database import Database
from .events import append_event
from .models import ValidationError, NotFoundError
from .service import Service, identifier, timestamp
from .workers import resolve
from .approvals import authorize, proposal
from .inputs import operation
from .verification import VerificationService
from .dependencies import DependencyService


def _invoke(sender, handler, snapshot):
    try:
        result = handler(snapshot)
        sender.send((True, result))
    except BaseException:
        sender.send((False, traceback.format_exc(limit=15)))
    finally:
        sender.close()


class ExecutionService:
    def __init__(self, database: Database, *, registry=None, timeout: float = 10):
        if not 0 < timeout <= 60:
            raise ValidationError("timeout must be between 0 and 60 seconds")
        self.database, self.registry, self.timeout = database, registry, timeout

    def get(self, execution_id: str) -> dict:
        with self.database.connect() as c:
            row = c.execute("SELECT * FROM executions WHERE id=?", (identifier(execution_id),)).fetchone()
            if row is None:
                raise NotFoundError("Execution not found")
            result = dict(row)
            raw = result.pop("result_json")
            result["result"] = json.loads(raw) if raw else None
            if result["worker_id"] in ("csv-profile", "research-collect"):
                latest = c.execute("SELECT id, status, verified_at FROM verifications WHERE execution_id=? ORDER BY rowid DESC LIMIT 1", (result["id"],)).fetchone()
                result["latest_verification"] = dict(latest) if latest else None
            return result

    def history(self, task_id: str) -> list[dict]:
        with self.database.connect() as c:
            Service(self.database)._get(c, "tasks", task_id)
            ids = [r[0] for r in c.execute("SELECT id FROM executions WHERE task_id=? ORDER BY attempt", (identifier(task_id),))]
        return [self.get(i) for i in ids]

    def events(self, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValidationError("limit must be 1..1000")
        with self.database.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events ORDER BY rowid DESC LIMIT ?", (limit,))]

    def execute(self, task_id: str, worker_id: str) -> dict:
        worker = resolve(worker_id, self.registry)
        service = Service(self.database)
        execution_id = str(uuid4())
        with self.database.connect(write=True) as c:
            task = service._get(c, "tasks", task_id)
            project = service._get(c, "projects", task["project_id"])
            if task["status"] != "pending":
                raise ValidationError("Only pending tasks can execute")
            if c.execute("SELECT 1 FROM executions WHERE status='running'").fetchone():
                raise ValidationError("An execution is already running; inspect history before recovery")
            DependencyService(self.database).enforce(c, task["id"])
            approval_id = authorize(c, self.database, task["id"], worker_id, worker, self.timeout)
            proposed, _ = proposal(c, self.database, task["id"], worker_id, worker, self.timeout)
            effective_timeout = proposed["timeout"]
            csv_content = None
            if worker_id == "csv-profile":
                csv_input, csv_content = operation(c, self.database, task["id"])
                if csv_input != proposed["csv_input"]:
                    raise ValidationError("CSV input changed while claiming execution")
            attempt = c.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM executions WHERE task_id=?", (task["id"],)).fetchone()[0]
            now = timestamp()
            c.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)", (execution_id, task["id"], worker_id, "running", now, None, attempt, None, None, None))
            if worker_id == "research-collect":
                from .research import canonical, digest
                c.execute("INSERT INTO research_runs VALUES (?,?,?,NULL)", (execution_id, canonical(proposed["research"]), digest(proposed["research"])))
            if csv_content is not None:
                c.execute("INSERT INTO execution_inputs VALUES (?,?,?,?,?,?)", (execution_id, csv_input["input_id"], csv_input["sha256"], json.dumps(csv_input["limits"]), worker.version, None))
            c.execute("INSERT INTO execution_ownership VALUES (?,?,?,?,?,?)", (execution_id, socket.gethostname(), os.getpid(), None, "not_started", now))
            if approval_id:
                c.execute("UPDATE approvals SET execution_id=? WHERE id=?", (execution_id, approval_id))
                append_event(c, "execution_resumed_after_approval", task["id"], execution_id, {"approval_id": approval_id})
            append_event(c, "execution_requested", task["id"], execution_id, {"worker": worker_id})
            c.execute("UPDATE tasks SET status='in_progress', updated_at=? WHERE id=?", (now, task["id"]))
            append_event(c, "execution_started", task["id"], execution_id)
        result, error = None, None
        try:
            snapshot = {"snapshot_at": timestamp(), "project": proposed["project"], "tasks": proposed["tasks"]}
            for record in snapshot["tasks"]:
                if record["id"] == task["id"]:
                    record.update(status="in_progress", updated_at=now)
            if len(json.dumps(snapshot).encode("utf-8")) > 8_000_000:
                raise ValidationError("Report snapshot exceeds 8 MB limit")
            if csv_content is not None:
                snapshot = {"snapshot_at": timestamp(), "csv_bytes": csv_content, "csv_input": csv_input, "worker_version": worker.version}
            if worker_id == "research-collect":
                snapshot = {"research": proposed["research"], "execution_id": execution_id}
            context = multiprocessing.get_context("spawn")
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=_invoke, args=(sender, worker.handler, snapshot))
            try:
                with self.database.connect(write=True) as c:
                    c.execute("UPDATE execution_ownership SET phase='starting', recorded_at=? WHERE execution_id=?", (timestamp(), execution_id))
                process.start()
                with self.database.connect(write=True) as c:
                    c.execute("UPDATE execution_ownership SET phase='running', child_pid=?, recorded_at=? WHERE execution_id=?", (process.pid, timestamp(), execution_id))
                sender.close()
                if not receiver.poll(effective_timeout):
                    raise TimeoutError(f"Worker exceeded {effective_timeout} seconds")
                ok, output = receiver.recv()
                if not ok:
                    raise RuntimeError(output)
                worker.validator(snapshot, output)
            finally:
                if process.pid is not None:
                    process.join(0.2)
                    if process.is_alive():
                        process.terminate()
                        process.join(5)
                    if process.is_alive():
                        raise RuntimeError("Child termination unconfirmed; running claim retained")
                    with self.database.connect(write=True) as c:
                        c.execute("UPDATE execution_ownership SET phase='stopped', recorded_at=? WHERE execution_id=?", (timestamp(), execution_id))
                    process.close()
                receiver.close()
                sender.close()
            if worker_id == "research-collect":
                from .research import canonical, digest
                with self.database.connect(write=True) as c:
                    c.execute("INSERT INTO research_captures VALUES (?,?,?)", (execution_id, canonical(output["captures"]), digest(output["captures"])))
            # Only engine-generated UUID names; exclusive creation prevents overwrites.
            data_dir = self.database.path.resolve().parent
            artifact_dir = data_dir / "artifacts"
            artifact_dir.mkdir(exist_ok=True)
            if artifact_dir.is_symlink() or artifact_dir.resolve() != data_dir / "artifacts":
                raise ValidationError("Artifact directory must not redirect outside data directory")
            artifact = artifact_dir / f"{execution_id}.json"
            temporary = artifact.with_suffix(".json.partial")
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(output, handle, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            # Hard-link publication is atomic and refuses an existing destination.
            os.link(temporary, artifact)
            temporary.unlink()
            worker.validator(snapshot, json.loads(artifact.read_text(encoding="utf-8")))
            result = {"artifact": str(artifact), "task_count": len(snapshot.get("tasks", [])),
                      "output_validated": True, "independent_evaluation": False}
            if csv_content is not None:
                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                with self.database.connect(write=True) as c:
                    c.execute("UPDATE execution_inputs SET artifact_digest=? WHERE execution_id=?", (digest, execution_id))
                verified = VerificationService(self.database).verify(execution_id)
                result.update(artifact_id=execution_id, input_id=csv_input["input_id"], row_count=output.get("row_count"), column_count=output.get("column_count"), artifact_sha256=digest, verification_id=verified["id"], verification_status=verified["status"], independent_evaluation=verified["status"] == "passed")
                if verified["status"] != "passed":
                    raise ValidationError("Independent CSV verification failed")
            if worker_id == "research-collect":
                from .research_verify import ResearchVerifier
                with self.database.connect(write=True) as c:
                    c.execute("UPDATE research_runs SET artifact_digest=? WHERE execution_id=?", (hashlib.sha256(artifact.read_bytes()).hexdigest(), execution_id))
                verified = ResearchVerifier(self.database).verify(execution_id)
                result.update(record_count=len(output['records']), verification_id=verified['id'], verification_status=verified['status'], independent_evaluation=verified['status']=='passed')
                if verified['status'] != 'passed':
                    raise ValidationError('Independent research provenance verification failed')
                if not any(p['status']=='ok' for p in output['providers']):
                    raise ValidationError('All research providers failed; evidence packet preserved')
        except (Exception, KeyboardInterrupt):
            error = traceback.format_exc(limit=15)
        status = "failed" if error else "succeeded"
        summary = "Worker failed; inspect execution error and verification history" if error else "CSV report independently verified" if csv_content is not None else "Report saved and validated against captured records"
        if worker_id == "research-collect" and not error:
            summary = "Research evidence collected and provenance verified; inspect provider failures and limitations"
        with self.database.connect(write=True) as c:
            owner = c.execute("SELECT phase FROM execution_ownership WHERE execution_id=?", (execution_id,)).fetchone()
            if owner[0] not in ("not_started", "stopped"):
                raise RuntimeError("Child termination evidence incomplete; inspect recovery before proceeding")
            final_readiness = DependencyService(self.database).explain(task["id"], connection=c)
            if any(not p["satisfied"] for p in final_readiness["prerequisites"]):
                error = (error or "") + "\nPrerequisite evidence changed during execution; result is not eligible for success"
                status, summary = "failed", "Dependency evidence invalidated during execution"
            now = timestamp()
            c.execute("UPDATE executions SET status=?, finished_at=?, summary=?, result_json=?, error=? WHERE id=? AND status='running'",
                      (status, now, summary, json.dumps(result) if result else None, error, execution_id))
            c.execute("UPDATE tasks SET status=?, updated_at=?, summary=? WHERE id=?", ("failed" if error else "completed", now, summary, task["id"]))
            append_event(c, "execution_" + status, task["id"], execution_id, {"output_validated": not bool(error)})
        return self.get(execution_id)
