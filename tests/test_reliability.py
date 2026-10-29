import json
import os
import socket
import sqlite3
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import test_foundation
from orion.approvals import ApprovalService
from orion.database import Database, SCHEMA, MIGRATION_2
from orion.execution import ExecutionService
from orion.models import ValidationError
from orion.recovery import RecoveryService, process_state
from orion.service import timestamp
from orion.workers import REGISTRY


def short_worker(snapshot):
    import time
    time.sleep(2)
    from orion.workers import project_report
    return project_report(snapshot)


class ReliabilityTests(unittest.TestCase):
    cli = test_foundation.FoundationTests.cli

    def setUp(self):
        test_foundation.FoundationTests.setUp(self)
        self.task = self.service.create_task(self.project["id"], "Guarded report", require_approval=True)
        self.approvals = ApprovalService(self.db)
        self.engine = ExecutionService(self.db)
        self.recovery = RecoveryService(self.db)

    def approve(self):
        request = self.approvals.request(self.task["id"], "project-status", "Review exact report")
        return self.approvals.decide(request["id"], "approved", "Reviewed")

    def execute(self):
        return self.engine.execute(self.task["id"], "project-status")

    def fixture(self, phase="not_started", child_pid=None, parent_pid=None):
        if parent_pid is None:
            proc = subprocess.Popen([sys.executable, "-c", "pass"])
            parent_pid = proc.pid
            proc.wait(timeout=5)
        eid = str(uuid4())
        with self.db.connect(write=True) as c:
            c.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)", (eid, self.task["id"], "project-status", "running", timestamp(), None, 1, None, None, None))
            c.execute("UPDATE tasks SET status='in_progress' WHERE id=?", (self.task["id"],))
            c.execute("INSERT INTO execution_ownership VALUES (?,?,?,?,?,?)", (eid, socket.gethostname(), parent_pid, child_pid, phase, timestamp()))
        return eid

    def test_missing_pending_rejected_and_direct_service(self):
        with self.assertRaises(ValidationError): self.execute()
        request = self.approvals.request(self.task["id"], "project-status", "Review")
        with self.assertRaises(ValidationError): self.execute()
        self.approvals.decide(request["id"], "rejected", "Not ready")
        with self.assertRaises(ValidationError): self.execute()
        self.assertEqual(self.engine.history(self.task["id"]), [])
        self.assertEqual(self.service.get("tasks", self.task["id"])["status"], "pending")

    def test_approval_success_and_no_autoexecution(self):
        request = self.approve()
        self.assertEqual(self.engine.history(self.task["id"]), [])
        result = self.execute()
        self.assertEqual(result["status"], "succeeded", result["error"])
        self.assertEqual(self.approvals.get(request["id"])["execution_id"], result["id"])
        events = [row["type"] for row in self.engine.events()]
        self.assertIn("approval_granted", events)
        self.assertIn("execution_resumed_after_approval", events)

    def test_stale_task_and_project_inputs(self):
        self.approve()
        self.service.update("tasks", self.task["id"], title="Edited action")
        with self.assertRaises(ValidationError): self.execute()
        self.approve()
        self.service.update("projects", self.project["id"], description="Changed source")
        with self.assertRaises(ValidationError): self.execute()
        self.assertIn("approval_invalidated", [e["type"] for e in self.engine.events()])

    def test_other_task_worker_version_and_configuration(self):
        self.approve()
        another = self.service.create_task(self.project["id"], "Other", require_approval=True)
        with self.assertRaises(ValidationError): self.engine.execute(another["id"], "project-status")
        self.approve()
        for key, worker, timeout in (("other", REGISTRY["project-status"], 10), ("project-status", replace(REGISTRY["project-status"], version="2"), 10), ("project-status", REGISTRY["project-status"], 9)):
            with self.subTest(key=key, version=worker.version, timeout=timeout):
                with self.assertRaises(ValidationError):
                    ExecutionService(self.db, registry={key: worker}, timeout=timeout).execute(self.task["id"], key)

    def test_duplicate_invalid_decisions_and_restart(self):
        req = self.approvals.request(self.task["id"], "project-status", "Review")
        self.assertEqual(json.loads(self.cli("approvals", "pending").stdout)[0]["id"], req["id"])
        for decision in ("pending", "nonsense"):
            with self.assertRaises(ValidationError): self.approvals.decide(req["id"], decision, "why")
        self.assertEqual(self.cli("approvals", "decide", req["id"], "approved", "--reason", "Reviewed").returncode, 0)
        for decision in ("approved", "rejected"):
            with self.assertRaises(ValidationError): self.approvals.decide(req["id"], decision, "Again")
        self.assertEqual(json.loads(self.cli("approvals", "get", req["id"]).stdout)["status"], "approved")

    def test_failed_attempt_consumes_approval(self):
        self.approve()
        (self.root / "artifacts").write_text("obstruction")
        self.assertEqual(self.execute()["status"], "failed")
        self.service.transition("tasks", self.task["id"], "pending")
        with self.assertRaises(ValidationError): self.execute()

    def test_recovery_terminal_preserves_artifact(self):
        self.approve()
        result = self.execute()
        artifact = Path(result["result"]["artifact"])
        before = artifact.read_bytes()
        self.assertFalse(self.recovery.inspect(result["id"])["safe_to_recover"])
        with self.assertRaises(ValidationError): self.recovery.confirm(result["id"], "Do not change")
        self.assertEqual(self.engine.get(result["id"]), result)
        self.assertEqual(artifact.read_bytes(), before)

    def test_active_parent_refused(self):
        eid = self.fixture(parent_pid=os.getpid())
        self.assertFalse(self.recovery.inspect(eid)["safe_to_recover"])
        with self.assertRaises(ValidationError): self.recovery.confirm(eid, "Still active")
        self.assertEqual(self.engine.get(eid)["status"], "running")

    def test_active_child_refused(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        try:
            eid = self.fixture(phase="running", child_pid=child.pid)
            evidence = self.recovery.inspect(eid)
            self.assertEqual(evidence["child_state"], "active")
            with self.assertRaises(ValidationError): self.recovery.confirm(eid, "Child still active")
        finally:
            child.terminate()
            child.wait(timeout=5)
        self.assertTrue(self.recovery.inspect(eid)["safe_to_recover"])

    def test_unknown_launch_and_legacy_remain_unresolved(self):
        eid = self.fixture(phase="starting")
        self.assertFalse(self.recovery.inspect(eid)["safe_to_recover"])
        with self.assertRaises(ValidationError): self.recovery.confirm(eid, "Unknown child")
        with self.db.connect(write=True) as c:
            c.execute("DELETE FROM execution_ownership WHERE execution_id=?", (eid,))
        with self.assertRaises(ValidationError): self.recovery.confirm(eid, "Legacy record")
        self.assertEqual(self.db.health()["integrity"], "ok")

    def test_recovery_concurrency_persistence_and_orphan_artifact(self):
        eid = self.fixture()
        folder = self.root / "artifacts"
        folder.mkdir()
        artifact = folder / (eid + ".json")
        artifact.write_text("unverified partial artifact")
        original = self.engine.get(eid)
        self.assertTrue(self.recovery.inspect(eid)["safe_to_recover"])
        command = [sys.executable, "-m", "orion", "--database", str(self.db.path), "--log-dir", str(self.root / "logs"), "recovery", "confirm", eid, "--reason", "Owner stopped; preserve partial output"]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        for p in processes: p.communicate(timeout=10)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        recovered = json.loads(self.cli("execution", eid).stdout)
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(recovered["started_at"], original["started_at"])
        self.assertEqual(self.service.get("tasks", self.task["id"])["status"], "blocked")
        self.assertEqual(artifact.read_text(), "unverified partial artifact")
        self.assertIn("recovery_authorized", [e["type"] for e in self.engine.events()])
        with self.assertRaises(ValidationError): self.execute()

    def test_schema2_migration_preserves_execution_events(self):
        old = Database(self.root / "old.sqlite3")
        pid, tid, eid, event = (str(uuid4()) for _ in range(4))
        with old.connect(write=True) as c:
            for sql in (*SCHEMA, *MIGRATION_2): c.execute(sql)
            c.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)", (pid,"old","","active","then","then"))
            c.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", (tid,pid,"old","","completed",0,"then","then",None))
            c.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)", (eid,tid,"project-status","succeeded","then","later",1,"kept",'{}',None))
            c.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (event,"then","execution_succeeded",tid,eid,'{}'))
            c.execute("PRAGMA user_version=2")
        old.initialize()
        old.initialize()
        self.assertEqual(ExecutionService(old).get(eid)["summary"], "kept")
        self.assertEqual(ExecutionService(old).events()[0]["id"], event)
        self.assertEqual(old.health()["schema_version"], 6)

    def test_actual_parent_crash_with_live_child(self):
        import time
        # Unprotected test task: only this test process is intentionally terminated.
        task = self.service.create_task(self.project["id"], "Crash fixture")
        script = "from pathlib import Path; from test_reliability import short_worker; from dataclasses import replace; from orion.workers import REGISTRY; from orion.execution import ExecutionService; from orion.database import Database; import sys; ExecutionService(Database(Path(sys.argv[1])),registry={'test':replace(REGISTRY['project-status'],handler=short_worker)}).execute(sys.argv[2],'test')"
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).parent))
        parent = subprocess.Popen([sys.executable,"-c",script,str(self.db.path),task["id"]], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 8
            owner = None
            while time.monotonic() < deadline:
                with self.db.connect() as c:
                    owner = c.execute("SELECT * FROM execution_ownership WHERE phase='running'").fetchone()
                if owner: break
                time.sleep(0.02)
            self.assertIsNotNone(owner)
            parent.terminate()
            parent.wait(timeout=5)
            eid = owner["execution_id"]
            evidence = self.recovery.inspect(eid)
            self.assertFalse(evidence["safe_to_recover"])
            self.assertEqual(evidence["child_state"], "active")
            deadline = time.monotonic() + 8
            while process_state(owner["child_pid"]) != "stopped" and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(self.recovery.inspect(eid)["safe_to_recover"])
            self.recovery.confirm(eid, "Test parent terminated and child exit observed")
            self.assertEqual(self.engine.get(eid)["status"], "failed")
        finally:
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=5)
