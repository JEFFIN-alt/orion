"""Separate saved-file verification. Never calls the worker or its validator."""
import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from uuid import uuid4
from .inputs import InputService, managed_dir, read_bounded, limits
from .models import ValidationError, NotFoundError
from .service import identifier, timestamp
from .events import append_event


def recount(raw, settings):
    """Independent streaming pass, separate from csv_worker.profile."""
    try:
        stream = io.StringIO(raw.decode("utf-8-sig"), newline="")
    except UnicodeError:
        raise ValidationError("Verification input encoding failed") from None
    previous = csv.field_size_limit(settings["max_field_size"])
    try:
        records = csv.reader(stream, delimiter=",", quotechar='"', doublequote=True, strict=True)
        header = next(records, [])
        names = [value.strip() for value in header]
        if not names or any(not n for n in names) or len(set(names)) != len(names):
            raise ValidationError("Verification header check failed")
        if len(names) > settings["max_columns"]: raise ValidationError("Verification column limit exceeded")
        missing = [0] * len(names)
        numbers = [0] * len(names)
        totals = [Decimal(0) for _ in names]
        lows, highs = [None] * len(names), [None] * len(names)
        text_columns = set()
        rows = 0
        with localcontext() as context:
            context.prec = 50
            for values in records:
                rows += 1
                if rows > settings["max_rows"] or len(values) != len(names): raise ValidationError("Verification row shape or row limit failed")
                for index, cell in enumerate(values):
                    value = cell.strip()
                    if not value:
                        missing[index] += 1
                    else:
                        try:
                            if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value): raise InvalidOperation
                            number = Decimal(value)
                            if not number.is_finite() or (number != 0 and not -308 <= number.adjusted() <= 308): raise InvalidOperation
                            numbers[index] += 1
                            totals[index] += number
                            lows[index] = number if lows[index] is None else min(lows[index], number)
                            highs[index] = number if highs[index] is None else max(highs[index], number)
                        except InvalidOperation:
                            text_columns.add(index)
            expected = []
            for index, name in enumerate(names):
                count = rows - missing[index]
                numeric = count > 0 and index not in text_columns
                expected.append({"header": name, "non_missing": count, "missing": missing[index],
                    "type": "numeric" if numeric else "empty" if count == 0 else "text",
                    "checks": ["all_rows", "blank_missing", "finite_decimal"],
                    "numeric": {"count": count, "minimum": str(lows[index]), "maximum": str(highs[index]), "mean": str(totals[index] / count)} if numeric else None})
        return rows, len(names), expected
    except csv.Error:
        raise ValidationError("Verification CSV syntax or field-size check failed") from None
    finally:
        csv.field_size_limit(previous)


class VerificationService:
    def __init__(self, database):
        self.database = database

    def history(self, execution_id):
        with self.database.connect() as c:
            if not c.execute("SELECT 1 FROM executions WHERE id=?", (identifier(execution_id),)).fetchone(): raise NotFoundError("Execution not found")
            records = [dict(row) for row in c.execute("SELECT * FROM verifications WHERE execution_id=? ORDER BY rowid", (identifier(execution_id),))]
        for record in records:
            record["checks"] = json.loads(record.pop("checks_json"))
        return records

    def verify(self, execution_id):
        execution_id = identifier(execution_id)
        with self.database.connect() as c:
            synthesis = c.execute("SELECT 1 FROM synthesis_runs WHERE execution_id=?", (execution_id,)).fetchone()
            research = c.execute("SELECT 1 FROM research_runs WHERE execution_id=?", (execution_id,)).fetchone()
        if synthesis:
            from .synthesis_verify import SynthesisVerifier
            return SynthesisVerifier(self.database).verify(execution_id)
        if research:
            from .research_verify import ResearchVerifier
            return ResearchVerifier(self.database).verify(execution_id)
        with self.database.connect() as c:
            execution = c.execute("SELECT * FROM executions WHERE id=?", (execution_id,)).fetchone()
            binding = c.execute("SELECT * FROM execution_inputs WHERE execution_id=?", (execution_id,)).fetchone()
            if execution is None or binding is None: raise ValidationError("Execution has no CSV verification binding")
        checks, artifact_digest, input_digest = [], None, None
        def check(name, passed):
            checks.append({"name": name, "passed": bool(passed)})
            if not passed: raise ValidationError(name + " failed")
        stage = "input_read"
        try:
            settings = limits(json.loads(binding["limits_json"]))
            asset, raw = InputService(self.database).read(binding["input_id"], settings["max_bytes"])
            input_digest = hashlib.sha256(raw).hexdigest()
            check("input_digest", input_digest == binding["sha256"])
            stage = "artifact_read"
            artifact = managed_dir(self.database, "artifacts") / (execution_id + ".json")
            saved = read_bounded(artifact, 4 * 1024 * 1024)
            artifact_digest = hashlib.sha256(saved).hexdigest()
            check("artifact_digest", artifact_digest == binding["artifact_digest"])
            stage = "artifact_json"
            def reject_constant(value): raise ValueError("Nonfinite JSON")
            def unique_keys(pairs):
                result = {}
                for key, value in pairs:
                    if key in result: raise ValueError("Duplicate JSON key")
                    result[key] = value
                return result
            report = json.loads(saved, parse_constant=reject_constant, object_pairs_hook=unique_keys)
            fields = {"schema_version", "worker_id", "worker_version", "input_id", "input_sha256", "input_size", "analysis_at", "row_count", "column_count", "columns"}
            check("report_schema", isinstance(report, dict) and set(report) == fields and type(report["schema_version"]) is int and report["schema_version"] == 1)
            check("worker_binding", report["worker_id"] == "csv-profile" and report["worker_version"] == binding["worker_version"])
            check("asset_binding", report["input_id"] == asset["id"] and report["input_sha256"] == input_digest and type(report["input_size"]) is int and report["input_size"] == len(raw))
            stage = "analysis_timestamp"
            check("analysis_timestamp", isinstance(report["analysis_at"], str) and datetime.fromisoformat(report["analysis_at"]).tzinfo is not None)
            stage = "independent_csv_pass"
            rows, columns, expected = recount(raw, settings)
            check("row_count", type(report["row_count"]) is int and report["row_count"] == rows)
            check("column_count", type(report["column_count"]) is int and report["column_count"] == columns)
            check("column_counts_types_and_numeric_summaries", json.dumps(report["columns"], sort_keys=True) == json.dumps(expected, sort_keys=True))
            stage = "final_digest_check"
            _, latest = InputService(self.database).read(binding["input_id"], settings["max_bytes"])
            check("input_unchanged", hashlib.sha256(latest).hexdigest() == input_digest)
            check("artifact_unchanged", hashlib.sha256(read_bounded(artifact, 4 * 1024 * 1024)).hexdigest() == artifact_digest)
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            if not checks or checks[-1]["passed"]:
                checks.append({"name": stage, "passed": False, "error_type": type(exc).__name__})
        passed = bool(checks) and all(item["passed"] for item in checks)
        record_id = str(uuid4())
        with self.database.connect(write=True) as c:
            c.execute("INSERT INTO verifications VALUES (?,?,?,?,?,?,?,?,?,?)", (record_id, execution_id, "csv-independent", "1", "passed" if passed else "failed", input_digest, artifact_digest, timestamp(), json.dumps(checks), "Saved bytes independently verified" if passed else "Verification failed; inspect individual checks"))
            append_event(c, "verification_passed" if passed else "verification_failed", execution["task_id"], execution_id, {"verification_id": record_id})
        return next(row for row in self.history(execution_id) if row["id"] == record_id)
