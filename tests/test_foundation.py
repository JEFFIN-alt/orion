import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from orion.database import Database
from orion.models import TASK_TRANSITIONS, PROJECT_TRANSITIONS, ValidationError
from orion.service import Service


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "state.sqlite3")
        self.db.initialize()
        self.service = Service(self.db)
        self.project = self.service.create_project("Example")

    def test_initialization_preserves_records(self):
        self.db.initialize()
        self.assertEqual(Service(Database(self.db.path)).get("projects", self.project["id"]), self.project)
        self.assertEqual(self.db.health()["integrity"], "ok")

    def test_foreign_keys_and_rollback(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect(write=True) as c:
                self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                c.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid4()), str(uuid4()), "x", "", "pending", 0, "now", "now", None))
        self.assertEqual(self.service.list("tasks"), [])

    def test_unknown_schema(self):
        with self.db.connect(write=True) as c:
            c.execute("PRAGMA user_version=99")
        with self.assertRaises(RuntimeError):
            self.db.initialize()

    def test_all_state_pairs(self):
        for kind, rules in (("tasks", TASK_TRANSITIONS), ("projects", PROJECT_TRANSITIONS)):
            for old in rules:
                for new in rules:
                    with self.subTest(kind=kind, old=old, new=new):
                        record = self.service.create_task(self.project["id"], "Task") if kind == "tasks" else self.service.create_project("Project")
                        with self.db.connect(write=True) as c:
                            c.execute(f"UPDATE {kind} SET status=?, updated_at=? WHERE id=?", (old, "2000-01-01", record["id"]))
                        before = self.service.get(kind, record["id"])
                        if new in rules[old]:
                            result = self.service.transition(kind, record["id"], new)
                            self.assertEqual(result["status"], new)
                            self.assertNotEqual(result["updated_at"], before["updated_at"])
                        else:
                            with self.assertRaises(ValidationError):
                                self.service.transition(kind, record["id"], new)
                            self.assertEqual(self.service.get(kind, record["id"]), before)

    def test_validation_and_updates(self):
        for name in ("", "   ", None):
            with self.assertRaises(ValidationError):
                self.service.create_project(name)
        for priority in (-1, 101, True, "2"):
            with self.assertRaises(ValidationError):
                self.service.create_task(self.project["id"], "task", priority=priority)
        for pid in ("", "invalid", str(uuid4())):
            with self.assertRaises(ValidationError):
                self.service.create_task(pid, "task")
        task = self.service.create_task(self.project["id"], "quote ' ; --")
        updated = self.service.update("tasks", task["id"], title="Updated", priority=10, summary="result")
        self.assertEqual(updated["summary"], "result")
        self.assertEqual(len(self.service.list("tasks", self.project["id"])), 1)
        with self.assertRaises(ValidationError):
            self.service.update("tasks", task["id"], status="completed")
        self.assertEqual(self.service.get("tasks", task["id"]), updated)
        self.service.transition("tasks", task["id"], "in_progress")
        result = self.service.transition("tasks", task["id"], "failed", "test failure")
        self.assertEqual(result["summary"], "test failure")
        self.assertEqual(self.service.update("projects", self.project["id"], name="Renamed")["name"], "Renamed")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "orion", "--database", str(self.db.path), "--log-dir", str(self.root / "logs"), *args], text=True, capture_output=True, timeout=15)

    def test_cli_fresh_process_workflow(self):
        self.assertEqual(self.cli("init").returncode, 0)
        result = self.cli("tasks", "create", "CLI task", "--project", self.project["id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        task_id = json.loads(result.stdout)["id"]
        self.assertEqual(json.loads(self.cli("tasks", "get", task_id).stdout)["title"], "CLI task")
        bad = self.cli("tasks", "transition", task_id, "completed")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("Invalid transition", bad.stderr)
        self.assertEqual(self.cli("tasks", "transition", task_id, "in_progress").returncode, 0)
        self.assertEqual(self.cli("tasks", "transition", task_id, "completed", "--summary", "Execution finished").returncode, 0)
        self.assertEqual(json.loads(self.cli("status").stdout)["integrity"], "ok")
        self.assertEqual(self.cli("tasks", "update", task_id).returncode, 1)
        self.assertEqual(self.cli("nonsense").returncode, 2)
        self.assertTrue((self.root / "logs" / "orion.log").is_file())

    def test_online_backup_integrity_schema_and_row_counts(self):
        task=self.service.create_task(self.project['id'],'Backed-up task')
        destination=self.root/'backup.sqlite3'
        result=self.cli('backup',str(destination))
        self.assertEqual(result.returncode,0,result.stderr)
        backup=sqlite3.connect(destination)
        try:
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            with self.db.connect() as source:
                self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],source.execute('PRAGMA user_version').fetchone()[0])
                tables=[r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for table in tables:
                    self.assertEqual(backup.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0],source.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0],table)
                self.assertEqual(backup.execute('SELECT id FROM tasks WHERE id=?',(task['id'],)).fetchone()[0],task['id'])
        finally:
            backup.close()

    def test_online_backup_refuses_existing_destination_unchanged(self):
        destination=self.root/'already-there.sqlite3';destination.write_bytes(b'keep me')
        result=self.cli('backup',str(destination))
        self.assertEqual(result.returncode,1)
        self.assertIn('already exists',result.stderr)
        self.assertEqual(destination.read_bytes(),b'keep me')

    def test_online_backup_succeeds_with_another_read_connection_open(self):
        destination=self.root/'concurrent.sqlite3'
        with self.db.connect() as reader:
            reader.execute('BEGIN')
            reader.execute('SELECT * FROM projects').fetchall()
            result=self.db.backup(destination)
            self.assertTrue(destination.is_file())
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM projects').fetchone()[0],1)
        backup=sqlite3.connect(destination)
        try:
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            with self.db.connect() as source:
                self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],source.execute('PRAGMA user_version').fetchone()[0])
                tables=[r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for table in tables:
                    self.assertEqual(backup.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0],source.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0],table)
        finally:
            backup.close()

    def test_backup_closes_source_when_destination_connection_open_fails(self):
        source=sqlite3.connect(self.db.path)
        destination=self.root/'failed-open.sqlite3'
        with patch('orion.database.sqlite3.connect',side_effect=[source,sqlite3.OperationalError('destination connection failed')]) as connect:
            with self.assertRaises(ValueError): self.db.backup(destination)
        self.assertEqual(connect.call_count,2)
        with self.assertRaises(sqlite3.ProgrammingError): source.execute('SELECT 1')
        self.assertFalse(destination.exists())
        self.assertFalse(destination.with_name(destination.name+'.partial').exists())

    def test_backup_publish_failure_leaves_no_target_or_partial(self):
        destination=self.root/'failed-publish.sqlite3'
        with patch('orion.database.os.link',side_effect=OSError('publish failed')):
            with self.assertRaises(ValidationError): self.db.backup(destination)
        self.assertFalse(destination.exists())
        self.assertFalse(destination.with_name(destination.name+'.partial').exists())

    def test_backup_stale_partial_is_refused_and_preserved(self):
        destination=self.root/'stale-partial.sqlite3'
        partial=destination.with_name(destination.name+'.partial')
        partial.write_bytes(b'preserve stale partial')
        with patch('orion.database.sqlite3.connect') as connect:
            with self.assertRaises(ValidationError): self.db.backup(destination)
        connect.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(partial.read_bytes(),b'preserve stale partial')

    def test_backup_refusals_open_no_sqlite_connections(self):
        existing=self.root/'exists.sqlite3';existing.write_bytes(b'already exists')
        dangling=self.root/'dangling-link.sqlite3'
        missing_parent=self.root/'missing'/'backup.sqlite3'
        missing_source=Database(self.root/'missing-source.sqlite3')
        with patch('orion.database.sqlite3.connect') as connect:
            with self.assertRaises(ValidationError): self.db.backup(existing)
            connect.assert_not_called()
            with patch.object(Path,'is_symlink',autospec=True,side_effect=lambda value:value==dangling):
                with self.assertRaises(ValidationError): self.db.backup(dangling)
            connect.assert_not_called()
            with self.assertRaises(ValidationError): self.db.backup(missing_parent)
            connect.assert_not_called()
            with self.assertRaises(ValidationError): missing_source.backup(missing_source.path)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
