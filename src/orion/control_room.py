"""Local control-room read models. Mutations delegate to existing services."""
import json
from dataclasses import asdict

from .approvals import ApprovalService, proposal
from .dependencies import DependencyService
from .execution import ExecutionService
from .models import ValidationError
from .research import ResearchService
from .service import Service, identifier
from .synthesis import SynthesisService
from .verification import VerificationService
from .workers import REGISTRY, resolve
from .task_lifecycle import TaskLifecycle
from .task_workers import binding


class ControlRoom:
    def __init__(self, database, config):
        self.database, self.config = database, config
        self.service = Service(database)

    def overview(self):
        with self.database.connect() as c:
            c.execute('BEGIN')
            counts = {name: c.execute('SELECT count(*) FROM '+name).fetchone()[0]
                      for name in ('projects', 'tasks', 'executions')}
            counts['pending_approvals'] = c.execute("SELECT count(*) FROM approvals WHERE status='pending'").fetchone()[0]
            statuses = {r['status']: r['n'] for r in c.execute('SELECT status,count(*) n FROM executions GROUP BY status')}
            executions = [dict(r) for r in c.execute('SELECT e.id,e.worker_id,e.status,e.started_at,e.finished_at,t.title task_title FROM executions e JOIN tasks t ON t.id=e.task_id ORDER BY e.rowid DESC LIMIT 8')]
            events = [dict(r) for r in c.execute('SELECT e.type,e.timestamp,e.execution_id,t.title task_title FROM events e JOIN tasks t ON t.id=e.task_id ORDER BY e.rowid DESC LIMIT 12')]
            claim = c.execute('SELECT uncertain,started_at FROM inference_claim').fetchone()
        return {'counts': counts, 'execution_statuses': statuses, 'recent_executions': executions,
                'activity': events, 'configuration': asdict(self.config),
                'inference_claim': dict(claim) if claim else None,
                'system': 'Local server responding', 'provider_reachability': 'Not checked',
                'model_loaded': 'Not checked'}

    def projects(self):
        projects = self.service.list('projects')
        tasks = self.service.list('tasks')
        for project in projects:
            selected = [t for t in tasks if t['project_id'] == project['id']]
            project['task_count'] = len(selected)
            project['completed_count'] = sum(t['status'] == 'completed' for t in selected)
        return projects

    def tasks(self, project=None):
        tasks = self.service.list('tasks', project)
        with self.database.connect() as c:
            bindings = {r['task_id']: r['worker_id'] for r in c.execute('SELECT task_id,worker_id FROM executions ORDER BY rowid')}
            for table, worker in (('research_operations','research-collect'),('synthesis_operations','research-synthesize'),('csv_operations','csv-profile')):
                for row in c.execute('SELECT task_id FROM '+table):
                    bindings[row['task_id']] = worker
            for task in tasks:
                assigned = binding(c, task['id'])
                if assigned:
                    bindings[task['id']] = assigned['worker_id']
        for task in tasks:
            task['worker'] = bindings.get(task['id'])
        return tasks

    def task(self, task_id):
        task = self.service.get('tasks', task_id)
        return {'task': task, 'dependency': DependencyService(self.database).explain(task_id),
                'history': ExecutionService(self.database).history(task_id),
                'lifecycle': TaskLifecycle(self.database).state(task_id)}

    def executions(self):
        with self.database.connect() as c:
            return [dict(r) for r in c.execute('SELECT e.id,e.task_id,t.title task_title,e.worker_id,e.status,e.attempt,e.started_at,e.finished_at FROM executions e JOIN tasks t ON t.id=e.task_id ORDER BY e.rowid DESC LIMIT 200')]

    def execution(self, execution_id):
        result = ExecutionService(self.database).get(execution_id)
        result['verifications'] = VerificationService(self.database).history(execution_id)
        return result

    def approval(self, approval_id):
        row = ApprovalService(self.database).get(approval_id)
        row['proposal'] = json.loads(row.pop('proposal_json'))
        row['task_title'] = self.service.get('tasks', row['task_id'])['title']
        row['can_decide'] = False
        row['eligibility'] = 'Consumed' if row['execution_id'] else row['status'].capitalize()
        if row['status'] == 'pending' and row['execution_id'] is None:
            try:
                with self.database.connect() as c:
                    c.execute('BEGIN')
                    task = self.service._get(c, 'tasks', row['task_id'])
                    _, current = proposal(c, self.database, row['task_id'], row['worker_id'], resolve(row['worker_id']))
                row['can_decide'] = task['status'] == 'pending' and current == row['fingerprint']
                row['eligibility'] = 'Current proposal' if row['can_decide'] else 'Stale proposal'
            except (ValueError, OSError):
                row['eligibility'] = 'Source or configuration unavailable'
        return row

    def approvals(self):
        with self.database.connect() as c:
            rows = [dict(r) for r in c.execute('SELECT a.id,a.task_id,t.title task_title,a.worker_id,a.status,a.execution_id,a.created_at FROM approvals a JOIN tasks t ON t.id=a.task_id ORDER BY a.rowid DESC LIMIT 200')]
        return rows

    def research(self):
        with self.database.connect() as c:
            research = [dict(r) for r in c.execute('SELECT t.id,t.title,t.status,r.config_json FROM research_operations r JOIN tasks t ON t.id=r.task_id ORDER BY t.created_at DESC')]
            synthesis = [dict(r) for r in c.execute('SELECT t.id,t.title,t.status,s.source_execution FROM synthesis_operations s JOIN tasks t ON t.id=s.task_id ORDER BY t.created_at DESC')]
        for row in research:
            row['configuration'] = json.loads(row.pop('config_json'))
        return {'collections': research, 'syntheses': synthesis}

    def evidence(self, execution_id):
        execution_id = identifier(execution_id)
        execution = ExecutionService(self.database).get(execution_id)
        if execution['worker_id'] == 'research-collect':
            return {'kind':'Collected evidence', 'packet': ResearchService(self.database).packet(execution_id),
                    'verifications': VerificationService(self.database).history(execution_id)}
        if execution['worker_id'] == 'research-synthesize':
            with self.database.connect() as c:
                row = c.execute('SELECT operation_json FROM synthesis_runs WHERE execution_id=?',(execution_id,)).fetchone()
            if row is None:
                raise ValidationError('Synthesis provenance unavailable')
            operation = json.loads(row['operation_json'])
            result = {'kind':'AI-generated analysis; human review required', 'operation':operation,
                      'verifications':VerificationService(self.database).history(execution_id)}
            try:
                result['report'] = SynthesisService(self.database).summary(execution_id)
            except (ValueError, OSError):
                result['report'] = {'error':'No readable synthesis artifact. Inspect execution failure details.'}
            return result
        raise ValidationError('This execution has no research or synthesis report')

    @staticmethod
    def workers():
        return [worker.describe() for worker in REGISTRY.values()]
