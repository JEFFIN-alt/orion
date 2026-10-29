import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import replace
from uuid import uuid4
import test_foundation
import unittest
from orion.database import Database, SCHEMA
from orion.execution import ExecutionService
from orion.models import ValidationError
from orion.workers import REGISTRY


def failing(snapshot):
    raise ValueError("deliberate test failure")


def invalid(snapshot):
    return {"invented": True}


def slow(snapshot):
    time.sleep(10)


class ExecutionTests(unittest.TestCase):
    cli = test_foundation.FoundationTests.cli
    def setUp(self):
        test_foundation.FoundationTests.setUp(self)
        self.task = self.service.create_task(self.project["id"], "Report")
        self.engine = ExecutionService(self.db)

    def test_success_and_artifact(self):
        result = self.engine.execute(self.task["id"], "project-status")
        self.assertEqual(result["status"], "succeeded", result["error"])
        from pathlib import Path
        report = json.loads(Path(result["result"]["artifact"]).read_text())
        self.assertEqual(report["project"], self.project)
        self.assertEqual(report["counts"], {"in_progress": 1})
        self.assertEqual(report["tasks"][0]["id"], self.task["id"])
        self.assertTrue(result["started_at"] <= result["finished_at"])
        self.db.initialize()
        self.assertEqual(ExecutionService(Database(self.db.path)).history(self.task["id"])[0], result)
        self.assertEqual({e["type"] for e in self.engine.events()}, {"execution_requested", "execution_started", "execution_succeeded"})
        self.assertEqual(self.service.get("tasks", self.task["id"])["status"], "completed")

    def test_failure_output_and_timeout(self):
        for handler, expected in ((failing, "deliberate test failure"), (invalid, "does not match"), (slow, "exceeded")):
            with self.subTest(handler=handler.__name__):
                task = self.service.create_task(self.project["id"], "Failure test")
                worker = replace(REGISTRY["project-status"], handler=handler)
                result = ExecutionService(self.db, registry={"test": worker}, timeout=0.7).execute(task["id"], "test")
                self.assertEqual(result["status"], "failed")
                self.assertIn(expected, result["error"])
                self.assertTrue(result["finished_at"])
                self.assertEqual(self.service.get("tasks", task["id"])["status"], "failed")
                self.assertEqual(self.engine.history(task["id"])[0]["error"], result["error"])
        self.assertIn("execution_failed", [e["type"] for e in self.engine.events()])

    def test_reject_invalid_states_and_ids(self):
        for tid, worker in ((self.task["id"], "unknown"), (str(uuid4()), "project-status"), ("bad", "project-status")):
            with self.assertRaises(ValidationError):
                self.engine.execute(tid, worker)
        for state in ("in_progress", "blocked", "completed", "failed", "cancelled"):
            with self.db.connect(write=True) as c:
                c.execute("UPDATE tasks SET status=? WHERE id=?", (state, self.task["id"]))
            with self.assertRaises(ValidationError):
                self.engine.execute(self.task["id"], "project-status")
        self.assertEqual(self.engine.history(self.task["id"]), [])

    def test_concurrent_claim_and_manual_transition(self):
        # Real separate process holds a running claim while its trusted test handler waits.
        script = "from pathlib import Path; from test_execution import slow; from dataclasses import replace; from orion.workers import REGISTRY; from orion.execution import ExecutionService; from orion.database import Database; import sys; e=ExecutionService(Database(Path(sys.argv[1])),registry={'test':replace(REGISTRY['project-status'],handler=slow)},timeout=2); e.execute(sys.argv[2],'test')"
        import os
        env = dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).parent))
        child = subprocess.Popen([sys.executable, "-c", script, str(self.db.path), self.task["id"]], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.engine.history(self.task["id"]):
                    break
                time.sleep(0.03)
            self.assertTrue(self.engine.history(self.task["id"]))
            other = self.service.create_task(self.project["id"], "Other")
            for task in (self.task, other):
                with self.assertRaises(ValidationError):
                    self.engine.execute(task["id"], "project-status")
            with self.assertRaises(ValidationError):
                self.service.transition("tasks", self.task["id"], "pending")
            out, err = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 0, err)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()

    def test_migration_from_v1(self):
        old = Database(self.root / "old.sqlite3")
        with old.connect(write=True) as c:
            for sql in SCHEMA:
                c.execute(sql)
            c.execute("PRAGMA user_version=1")
            c.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)", tuple(self.project.values()))
            c.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", tuple(self.task.values()))
        old.initialize()
        old.initialize()
        from orion.service import Service
        self.assertEqual(Service(old).get("tasks", self.task["id"]), self.task)
        self.assertEqual(old.health()["schema_version"], 3)

    def test_events_immutable_and_blocked(self):
        self.service.transition("tasks", self.task["id"], "in_progress")
        self.service.transition("tasks", self.task["id"], "blocked")
        self.assertEqual(self.engine.events()[0]["type"], "task_blocked")
        for statement in ("DELETE FROM events", "UPDATE events SET type='changed'"):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.db.connect(write=True) as c:
                    c.execute(statement)

    def test_worker_cli_history(self):
        self.assertEqual(json.loads(self.cli("workers").stdout)[0]["identifier"], "project-status")
        executed = self.cli("execute", self.task["id"], "project-status")
        self.assertEqual(executed.returncode, 0, executed.stderr)
        result = json.loads(executed.stdout)
        self.assertEqual(json.loads(self.cli("history", self.task["id"]).stdout)[0]["id"], result["id"])
        self.assertEqual(json.loads(self.cli("execution", result["id"]).stdout)["status"], "succeeded")

    def test_missing_project(self):
        # Deliberately corrupt fixture verifies the engine does not trust foreign IDs.
        with sqlite3.connect(self.db.path) as c:
            c.execute("UPDATE tasks SET project_id=? WHERE id=?", (str(uuid4()), self.task["id"]))
        c.close()
        with self.assertRaises(ValidationError):
            self.engine.execute(self.task["id"], "project-status")
        self.assertEqual(self.engine.history(self.task["id"]), [])

    def test_artifact_failure_and_explicit_retry(self):
        obstruction = self.root / "artifacts"
        obstruction.write_text("do not overwrite")
        result = self.engine.execute(self.task["id"], "project-status")
        self.assertEqual(result["status"], "failed")
        self.assertIn("FileExistsError", result["error"])
        self.assertEqual(obstruction.read_text(), "do not overwrite")
        obstruction.unlink()
        self.service.transition("tasks", self.task["id"], "pending")
        result = self.engine.execute(self.task["id"], "project-status")
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(len(self.engine.history(self.task["id"])), 2)
