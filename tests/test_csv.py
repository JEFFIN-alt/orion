import hashlib
import json
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from decimal import Decimal
from uuid import uuid4
import test_foundation
from orion.inputs import InputService, DEFAULT_LIMITS
from orion.csv_worker import profile
from orion.verification import VerificationService
from orion.execution import ExecutionService
from orion.approvals import ApprovalService
from orion.models import ValidationError
from orion.workers import REGISTRY
from orion.database import Database, SCHEMA, MIGRATION_2, MIGRATION_3


def incorrect_worker(snapshot):
    output = profile(snapshot)
    output["row_count"] += 1
    return output


class CsvTests(unittest.TestCase):
    cli = test_foundation.FoundationTests.cli

    def setUp(self):
        test_foundation.FoundationTests.setUp(self)
        self.inputs = InputService(self.db)
        self.engine = ExecutionService(self.db)
        self.verifier = VerificationService(self.db)
        self.task = self.service.create_task(self.project["id"], "CSV profile")
        self.source = self.root / "source.csv"

    def asset(self, raw=b"name,value,empty\nAlice,1,\nBob,3, \nNA,,\n"):
        self.source.write_bytes(raw)
        return self.inputs.import_csv(self.source)

    def configured(self, raw=None, **limits):
        asset = self.asset() if raw is None else self.asset(raw)
        self.inputs.bind(self.task["id"], asset["id"], **limits)
        return asset

    def run_csv(self):
        return self.engine.execute(self.task["id"], "csv-profile")

    def saved(self):
        self.configured()
        result = self.run_csv()
        self.assertEqual(result["status"], "succeeded", result["error"])
        return result, Path(result["result"]["artifact"])

    def test_import_digest_and_safe_names(self):
        asset = self.asset()
        self.assertEqual(asset["sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(asset["original_name"], "source.csv")
        self.assertEqual(self.inputs.read(asset["id"])[1], self.source.read_bytes())
        self.assertEqual(len(self.inputs.list()), 1)
        for invalid in ("../source.csv", "", str(uuid4())):
            with self.assertRaises(ValidationError): self.inputs.read(invalid)
        with self.assertRaises(OSError): self.inputs.import_csv(self.root / "absent.csv")
        with self.assertRaises(ValidationError): self.inputs.import_csv(self.source, max_bytes=2)

    def test_managed_filename_corruption_refused(self):
        asset = self.asset()
        with self.db.connect(write=True) as c:
            c.execute("UPDATE inputs SET filename='../source.csv' WHERE id=?", (asset["id"],))
        with self.assertRaises(ValidationError): self.inputs.read(asset["id"])
        self.assertTrue(self.source.exists())

    def test_redirected_input_directory_refused(self):
        # A regular-file obstruction must never be overwritten.
        (self.root / "inputs").write_text("preserve")
        with self.assertRaises(OSError): self.asset()
        self.assertEqual((self.root / "inputs").read_text(), "preserve")

    def test_correct_analysis_and_fresh_process_verification(self):
        result, artifact = self.saved()
        report = json.loads(artifact.read_text())
        self.assertEqual((report["row_count"], report["column_count"]), (3, 3))
        self.assertEqual([c["missing"] for c in report["columns"]], [0, 1, 3])
        numeric = report["columns"][1]["numeric"]
        self.assertEqual(numeric, {"count": 2, "minimum": "1", "maximum": "3", "mean": "2"})
        self.assertEqual(report["columns"][0]["type"], "text")
        self.assertEqual(report["columns"][2]["type"], "empty")
        self.assertNotIn(str(self.root), artifact.read_text())
        records = json.loads(self.cli("verifications", result["id"]).stdout)
        self.assertEqual(records[0]["status"], "passed")
        self.assertTrue(result["result"]["independent_evaluation"])
        self.assertFalse(artifact.with_suffix(".json.partial").exists())

    def test_determinism_bom_and_header_only(self):
        asset = self.asset(b"\xef\xbb\xbfx,y\n")
        snapshot = {"csv_bytes": self.inputs.read(asset["id"])[1], "csv_input": {"input_id":asset["id"],"sha256":asset["sha256"],"limits":DEFAULT_LIMITS}, "worker_version":"1", "snapshot_at":"2026-10-29T00:00:00+00:00"}
        self.assertEqual(profile(snapshot), profile(snapshot))
        self.inputs.bind(self.task["id"], asset["id"])
        result = self.run_csv()
        self.assertEqual(result["status"], "succeeded", result["error"])
        report = json.loads(Path(result["result"]["artifact"]).read_text())
        self.assertEqual(report["row_count"], 0)

    def test_invalid_csv_cases_and_limits(self):
        cases = [(b"", {}), (b"a, \n1,2\n", {}), (b"a,a\n1,2\n", {}), (b"a, a \n1,2\n", {}), (b"a,b\n1\n", {}), (b"a\n\xff", {}), (b'a\n"unterminated', {}), (b"a\n1\n2\n", {"max_rows":1}), (b"a,b\n1,2\n", {"max_columns":1}), (b"a\nlong\n", {"max_field_size":3})]
        for raw, settings in cases:
            with self.subTest(raw=raw, limits=settings):
                self.task = self.service.create_task(self.project["id"], "Invalid CSV")
                self.configured(raw, **settings)
                result = self.run_csv()
                self.assertEqual(result["status"], "failed")
                self.assertEqual(self.service.get("tasks", self.task["id"])["status"], "failed")
                self.assertIsNotNone(result["error"])

    def test_numeric_policy(self):
        self.configured(b"a,b,c,d\n1,NaN,NA,1e308\ntext,2,null,1e308\n")
        result = self.run_csv()
        self.assertEqual(result["status"], "succeeded", result["error"])
        report = json.loads(Path(result["result"]["artifact"]).read_text())
        self.assertEqual([c["type"] for c in report["columns"]], ["text","text","text","numeric"])
        self.assertEqual(Decimal(report["columns"][3]["numeric"]["mean"]), Decimal('1e308'))

    def test_tampered_missing_and_malformed_artifacts(self):
        result, path = self.saved()
        original = path.read_bytes()
        for data in (b"not JSON", original + b" "):
            path.write_bytes(data)
            verification = self.verifier.verify(result["id"])
            self.assertEqual(verification["status"], "failed")
        path.unlink()
        self.assertEqual(self.verifier.verify(result["id"])["status"], "failed")
        self.assertEqual(len(self.verifier.history(result["id"])), 4)
        self.assertEqual(self.engine.get(result["id"])["latest_verification"]["status"], "failed")

    def test_independent_checks_detect_incorrect_reports(self):
        result, path = self.saved()
        original = json.loads(path.read_text())
        for field in ("input_sha256", "row_count", "column_count", "missing", "numeric", "malformed"):
            report = json.loads(json.dumps(original))
            if field == "input_sha256": report[field] = "0"*64
            elif field in ("row_count","column_count"): report[field] += 1
            elif field == "missing": report["columns"][0]["missing"] += 1
            elif field == "numeric": report["columns"][1]["numeric"]["mean"] = "999"
            path.write_text("{bad" if field == "malformed" else json.dumps(report))
            # Simulate bad bytes saved by a buggy worker: digest alone now matches.
            with self.db.connect(write=True) as c:
                c.execute("UPDATE execution_inputs SET artifact_digest=? WHERE execution_id=?", (hashlib.sha256(path.read_bytes()).hexdigest(), result["id"]))
            verification = self.verifier.verify(result["id"])
            self.assertEqual(verification["status"], "failed", field)

    def test_wrong_input_digest_and_growth(self):
        asset = self.configured()
        (self.root / "inputs" / asset["filename"]).write_bytes(b"x\n999\n")
        with self.assertRaises(ValidationError): self.run_csv()
        self.assertEqual(self.engine.history(self.task["id"]), [])
        with self.assertRaises(ValidationError): self.inputs.read(asset["id"], 2)

    def test_verification_failure_means_execution_failure(self):
        self.configured()
        registry = {"csv-profile":replace(REGISTRY["csv-profile"], handler=incorrect_worker)}
        result = ExecutionService(self.db, registry=registry).execute(self.task["id"], "csv-profile")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["result"]["verification_status"], "failed")
        self.assertEqual(self.verifier.history(result["id"])[0]["status"], "failed")
        self.assertEqual(self.service.get("tasks", self.task["id"])["status"], "failed")

    def test_csv_approval_input_and_limits_binding(self):
        asset = self.configured()
        approvals = ApprovalService(self.db)
        approvals.require(self.task["id"])
        with self.assertRaises(ValidationError): self.run_csv()
        request = approvals.request(self.task["id"], "csv-profile", "Review dataset")
        with self.assertRaises(ValidationError): self.run_csv()
        approvals.decide(request["id"], "approved", "Reviewed")
        self.inputs.bind(self.task["id"], asset["id"], max_rows=10)
        with self.assertRaises(ValidationError): self.run_csv()
        request = approvals.request(self.task["id"], "csv-profile", "Review limits")
        approvals.decide(request["id"], "approved", "Reviewed")
        registry={"csv-profile":replace(REGISTRY["csv-profile"],version="2")}
        with self.assertRaises(ValidationError): ExecutionService(self.db,registry=registry).execute(self.task["id"],"csv-profile")
        self.assertEqual(self.run_csv()["status"], "succeeded")

    def test_approved_file_changed_requires_new_asset(self):
        asset = self.configured()
        approvals = ApprovalService(self.db)
        request = approvals.request(self.task["id"], "csv-profile", "Review dataset")
        approvals.decide(request["id"], "approved", "Reviewed")
        (self.root / "inputs" / asset["filename"]).write_bytes(b"changed\n1\n")
        with self.assertRaises(ValidationError): self.run_csv()
        self.assertIsNone(approvals.get(request["id"])["execution_id"])

    def test_csv_cli(self):
        self.source.write_text("x,y\n1,2\n")
        asset = json.loads(self.cli("inputs", "import", str(self.source)).stdout)
        self.assertEqual(json.loads(self.cli("inputs", "get", asset["id"]).stdout)["size"], self.source.stat().st_size)
        self.assertEqual(self.cli("csv-config", self.task["id"], "--input", asset["id"]).returncode, 0)
        result = self.cli("execute", self.task["id"], "csv-profile")
        self.assertEqual(result.returncode, 0, result.stderr)
        execution = json.loads(result.stdout)
        self.assertEqual(self.cli("verify", execution["id"]).returncode, 0)

    def test_schema3_history_preserved(self):
        old=Database(self.root/'old.sqlite3')
        pid,tid,eid,aid,event=(str(uuid4()) for _ in range(5))
        with old.connect(write=True) as c:
            for sql in (*SCHEMA,*MIGRATION_2,*MIGRATION_3): c.execute(sql)
            c.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)",(pid,'old','','active','then','then'))
            c.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)",(tid,pid,'old','','blocked',0,'then','then',None))
            c.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)",(eid,tid,'project-status','failed','then','later',1,'interrupted',None,'retained'))
            c.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(aid,tid,'project-status','report','digest','{}','why','then','approved','later','yes',eid))
            c.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",(event,'then','recovery_authorized',tid,eid,'{}'))
            c.execute("INSERT INTO recoveries VALUES (?,?,?,?)",(eid,'later','reviewed','{}'))
            c.execute("PRAGMA user_version=3")
        old.initialize(); old.initialize()
        with old.connect() as c:
            self.assertEqual(c.execute('SELECT error FROM executions').fetchone()[0],'retained')
            self.assertEqual(c.execute('SELECT id FROM approvals').fetchone()[0],aid)
            self.assertEqual(c.execute('SELECT id FROM events').fetchone()[0],event)
            self.assertEqual(c.execute('SELECT reason FROM recoveries').fetchone()[0],'reviewed')
        self.assertEqual(old.health()['schema_version'],6)

    def test_import_hard_size_ceiling(self):
        self.source.write_bytes(b"x" * (DEFAULT_LIMITS["max_bytes"] + 1))
        with self.assertRaises(ValidationError): self.inputs.import_csv(self.source)
        self.assertEqual(self.inputs.list(), [])

    def test_input_tampering_after_success_is_recorded(self):
        result, artifact = self.saved()
        with self.db.connect() as c:
            asset_id = c.execute("SELECT input_id FROM execution_inputs WHERE execution_id=?", (result["id"],)).fetchone()[0]
        asset = self.inputs.get(asset_id)
        (self.root / "inputs" / asset["filename"]).write_bytes(b"changed\n")
        self.assertEqual(self.verifier.verify(result["id"])["status"], "failed")
        self.assertTrue(artifact.exists())

    def test_artifact_does_not_overwrite_existing_file(self):
        # Actual worker publication is covered by saved(); UUID naming makes collisions
        # unlikely, but the filesystem primitive must fail closed on an existing name.
        import os
        source, target = self.root / "partial", self.root / "existing"
        source.write_text("new")
        target.write_text("keep")
        with self.assertRaises(FileExistsError): os.link(source, target)
        self.assertEqual(target.read_text(), "keep")
