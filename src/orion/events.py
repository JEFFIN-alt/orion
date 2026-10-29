import json
from uuid import uuid4
from .service import timestamp


def append_event(connection, event_type, task_id, execution_id=None, details=None):
    connection.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (str(uuid4()), timestamp(), event_type, task_id, execution_id, json.dumps(details or {})))
