"""Streaming statistics over a bounded byte snapshot, without file or network tools."""
import csv
import io
import re
from decimal import Decimal, InvalidOperation, localcontext
from .models import ValidationError

NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def profile(snapshot):
    raw, metadata, settings = snapshot["csv_bytes"], snapshot["csv_input"], snapshot["csv_input"]["limits"]
    if len(raw) > settings["max_bytes"]: raise ValidationError("Input byte limit exceeded")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ValidationError("CSV is not valid UTF-8") from None
    old_limit = csv.field_size_limit(settings["max_field_size"])
    try:
        reader = csv.reader(io.StringIO(text, newline=""), dialect="excel", strict=True)
        headers = next(reader, None)
        if not headers or any(not name.strip() for name in headers): raise ValidationError("CSV requires nonempty headers")
        headers = [name.strip() for name in headers]
        if len(headers) > settings["max_columns"]: raise ValidationError("Column limit exceeded")
        if len(set(headers)) != len(headers): raise ValidationError("Duplicate CSV headers")
        states = [{"header": h, "non_missing": 0, "missing": 0, "numeric": True, "total": Decimal(0), "min": None, "max": None} for h in headers]
        row_count = 0
        with localcontext() as ctx:
            ctx.prec = 50
            for row in reader:
                row_count += 1
                if row_count > settings["max_rows"]: raise ValidationError("Row limit exceeded")
                if len(row) != len(headers): raise ValidationError(f"Row {row_count} has an inconsistent field count")
                for state, cell in zip(states, row):
                    value = cell.strip()
                    if not value:
                        state["missing"] += 1
                        continue
                    state["non_missing"] += 1
                    if not state["numeric"]: continue
                    try:
                        number = Decimal(value) if NUMBER.fullmatch(value) else Decimal("NaN")
                        if not number.is_finite() or (number and abs(number.adjusted()) > 308): raise InvalidOperation
                    except InvalidOperation:
                        state["numeric"] = False
                        continue
                    state["total"] += number
                    state["min"] = number if state["min"] is None else min(state["min"], number)
                    state["max"] = number if state["max"] is None else max(state["max"], number)
            columns = []
            for state in states:
                count = state["non_missing"]
                numeric = state["numeric"] and count > 0
                item = {k: state[k] for k in ("header", "non_missing", "missing")}
                item.update(type="numeric" if numeric else "empty" if count == 0 else "text", checks=["all_rows", "blank_missing", "finite_decimal"])
                item["numeric"] = {"count": count, "minimum": str(state["min"]), "maximum": str(state["max"]), "mean": str(state["total"] / count)} if numeric else None
                columns.append(item)
        return {"schema_version": 1, "worker_id": "csv-profile", "worker_version": snapshot["worker_version"],
                "input_id": metadata["input_id"], "input_sha256": metadata["sha256"], "input_size": len(raw),
                "analysis_at": snapshot["snapshot_at"], "row_count": row_count, "column_count": len(headers), "columns": columns}
    except csv.Error:
        raise ValidationError("Malformed CSV or field-size limit exceeded") from None
    finally:
        csv.field_size_limit(old_limit)


def validate_output(snapshot, result):
    if not isinstance(result, dict) or result.get("schema_version") != 1 or not isinstance(result.get("columns"), list):
        raise ValidationError("CSV worker returned an invalid report structure")
