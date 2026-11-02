"""Explicit worker bindings in the existing append-only task event history."""
import json

from .events import append_event
from .models import ValidationError
from .service import Service, timestamp
from .workers import resolve


def binding(connection, task_id):
    row = connection.execute("SELECT id,timestamp,details_json FROM events WHERE task_id=? AND type='worker_assigned' ORDER BY rowid DESC LIMIT 1", (task_id,)).fetchone()
    if row is None:
        return None
    return {'event_id':row['id'], 'assigned_at':row['timestamp'], **json.loads(row['details_json'])}


class TaskWorkers:
    def __init__(self, database):
        self.database = database

    def assign(self, task_id, worker_id):
        worker = resolve(worker_id)
        with self.database.connect(write=True) as c:
            task = Service(self.database)._get(c, 'tasks', task_id)
            if task['status'] != 'pending':
                raise ValidationError('Workers can only be assigned to pending tasks')
            previous = binding(c, task['id'])
            if previous and previous['worker_id'] == worker_id and previous['version'] == worker.version:
                return previous
            c.execute('INSERT OR IGNORE INTO approval_policy VALUES (?,?)', (task['id'], timestamp()))
            append_event(c, 'worker_assigned', task['id'], details={'worker_id':worker_id, 'version':worker.version})
            return binding(c, task['id'])
