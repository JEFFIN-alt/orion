"""Managed immutable-by-contract CSV assets; only the importer accepts a source path."""
import hashlib
import json
import os
import stat
from pathlib import Path
from uuid import uuid4
from .models import ValidationError, NotFoundError
from .service import Service, identifier, timestamp
from .events import append_event

DEFAULT_LIMITS = {"max_bytes": 10 * 1024 * 1024, "max_rows": 100000, "max_columns": 200, "max_field_size": 65536}


def limits(values=None):
    result = dict(DEFAULT_LIMITS)
    if values:
        if values.keys() - result.keys():
            raise ValidationError("Unknown CSV limit")
        result.update(values)
    for key, value in result.items():
        if type(value) is not int or not 1 <= value <= DEFAULT_LIMITS[key]:
            raise ValidationError(f"{key} must be 1..{DEFAULT_LIMITS[key]}")
    return result


def managed_dir(database, name):
    base = database.path.resolve().parent
    folder = base / name
    if folder.exists() and (folder.is_symlink() or folder.resolve() != folder):
        raise ValidationError("Managed directory redirects outside its location")
    folder.mkdir(exist_ok=True)
    return folder


def read_bounded(path, maximum):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValidationError("Linked paths are not accepted")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValidationError("Input must be a regular file")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValidationError("File changed during open")
        content = handle.read(maximum + 1)
    if len(content) > maximum:
        raise ValidationError("File size limit exceeded")
    return content


class InputService:
    def __init__(self, database):
        self.database = database

    def import_csv(self, source, max_bytes=DEFAULT_LIMITS["max_bytes"]):
        limits({"max_bytes": max_bytes})
        source = Path(source).expanduser().absolute()
        content = read_bounded(source, max_bytes)
        asset_id = str(uuid4())
        name = asset_id + ".csv"
        target = managed_dir(self.database, "inputs") / name
        with target.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # A database failure may leave an orphan; never register incomplete copies.
        with self.database.connect(write=True) as c:
            c.execute("INSERT INTO inputs VALUES (?,?,?,?,?,?)", (asset_id, name, source.name, hashlib.sha256(content).hexdigest(), len(content), timestamp()))
        return self.get(asset_id)

    def get(self, asset_id):
        with self.database.connect() as c:
            row = c.execute("SELECT * FROM inputs WHERE id=?", (identifier(asset_id),)).fetchone()
            if row is None: raise NotFoundError("Input asset not found")
            return dict(row)

    def list(self):
        with self.database.connect() as c:
            return [dict(row) for row in c.execute("SELECT * FROM inputs ORDER BY imported_at,id")]

    def read(self, asset_id, max_bytes=DEFAULT_LIMITS["max_bytes"]):
        asset = self.get(asset_id)
        name = identifier(asset_id) + ".csv"
        if asset["filename"] != name:
            raise ValidationError("Invalid managed filename")
        content = read_bounded(managed_dir(self.database, "inputs") / name, max_bytes)
        if len(content) != asset["size"] or hashlib.sha256(content).hexdigest() != asset["sha256"]:
            raise ValidationError("Managed input digest mismatch; import changed bytes as a new asset")
        return asset, content

    def bind(self, task_id, asset_id, **settings):
        settings = limits(settings)
        asset, _ = self.read(asset_id, settings["max_bytes"])
        with self.database.connect(write=True) as c:
            task = Service(self.database)._get(c, "tasks", task_id)
            if task["status"] != "pending": raise ValidationError("CSV configuration requires a pending task")
            c.execute("INSERT INTO csv_operations VALUES (?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET input_id=excluded.input_id, limits_json=excluded.limits_json, updated_at=excluded.updated_at", (task["id"], asset["id"], json.dumps(settings, sort_keys=True), timestamp()))
            append_event(c, "csv_input_bound", task["id"], details={"input_id": asset["id"], "digest": asset["sha256"]})
        return {"task_id": task["id"], "input_id": asset["id"], "limits": settings}


def operation(c, database, task_id):
    row = c.execute("SELECT * FROM csv_operations WHERE task_id=?", (task_id,)).fetchone()
    if row is None: raise ValidationError("Bind an imported input with csv-config before execution")
    settings = limits(json.loads(row["limits_json"]))
    asset, content = InputService(database).read(row["input_id"], settings["max_bytes"])
    return {"input_id": asset["id"], "sha256": asset["sha256"], "size": asset["size"], "limits": settings, "configured_at": row["updated_at"]}, content
