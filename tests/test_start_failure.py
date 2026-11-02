"""Regression: a worker process that cannot be started must fail the attempt, not wedge the engine."""
import multiprocessing.context as mc
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orion.database import Database
from orion.execution import ExecutionService
from orion.service import Service


class StartFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(Path(self.tmp.name) / "orion.sqlite3")
        self.db.initialize()
        self.service = Service(self.db)
        self.project = self.service.create_project("p")
        self.task = self.service.create_task(self.project["id"], "t")

    def test_failed_start_is_recorded_and_does_not_block_the_engine(self):
        with mock.patch.object(mc.SpawnProcess, "start", side_effect=OSError(12, "cannot allocate memory")):
            result = ExecutionService(self.db).execute(self.task["id"], "project-status")
        self.assertEqual(result["status"], "failed")
        self.assertIn("cannot allocate memory", result["error"])
        self.assertEqual(self.service.get("tasks", self.task["id"])["status"], "failed")
        with self.db.connect() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM executions WHERE status='running'").fetchone())
        # Explicit retry path still works once the machine has memory again.
        self.service.transition("tasks", self.task["id"], "pending")
        retry = ExecutionService(self.db).execute(self.task["id"], "project-status")
        self.assertEqual(retry["status"], "succeeded")
        self.assertEqual(retry["attempt"], 2)


if __name__ == "__main__":
    unittest.main()
