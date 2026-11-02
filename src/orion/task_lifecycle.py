"""Browser lifecycle operations composed from Orion's existing services."""
import json

from .approvals import ApprovalService, proposal
from .dependencies import DependencyService
from .execution import ExecutionService
from .inputs import InputService, DEFAULT_LIMITS, operation as csv_operation, read_bounded
from .models import ValidationError
from .research import ResearchService, DEFAULTS as RESEARCH_DEFAULTS, BOUNDS as RESEARCH_BOUNDS
from .service import Service, identifier
from .synthesis import SynthesisService, DEFAULTS as SYNTHESIS_DEFAULTS, BOUNDS as SYNTHESIS_BOUNDS
from .task_workers import binding
from .workers import REGISTRY, resolve


class TaskLifecycle:
    def __init__(self, database):
        self.database = database

    def catalog(self):
        specs = {
            'project-status': ({}, {}, 'Reads a captured project/task snapshot; no extra configuration.'),
            'csv-profile': ({'input_id':'', **DEFAULT_LIMITS}, {}, 'Select a previously imported managed CSV input ID.'),
            'research-collect': ({'question':'', **RESEARCH_DEFAULTS}, RESEARCH_BOUNDS, 'Bounded Crossref/GitHub collection. Execution makes HTTPS requests.'),
            'research-synthesize': ({'source_execution':'', **SYNTHESIS_DEFAULTS}, SYNTHESIS_BOUNDS, 'Requires a successful verified research execution in this project. Optional passages are exact source_id/field/start/end selections. Execution calls the configured model.')
        }
        return [{**w.describe(), 'defaults':specs[k][0], 'bounds':specs[k][1],
                 'configuration_help':specs[k][2], 'availability':'Registered; input and execution readiness are checked separately'}
                for k,w in REGISTRY.items()]

    def selected(self, task_id):
        with self.database.connect() as c:
            task = Service(self.database)._get(c, 'tasks', task_id)
            assigned = binding(c, task['id'])
        if assigned is None:
            raise ValidationError('Assign a registered worker first')
        worker = resolve(assigned['worker_id'])
        if worker.version != assigned['version']:
            raise ValidationError('Worker version changed; reassign and inspect configuration')
        return task, assigned

    def configuration(self, task_id):
        _, assigned = self.selected(task_id)
        worker = assigned['worker_id']
        if worker == 'project-status':
            return {}
        if worker == 'research-collect':
            return ResearchService(self.database).get(task_id)['configuration']
        if worker == 'research-synthesize':
            operation = SynthesisService(self.database).get(task_id)
            return {'source_execution':operation['source_execution'], **operation['configuration']}
        with self.database.connect() as c:
            operation, _ = csv_operation(c, self.database, task_id)
        return {'input_id':operation['input_id'], **operation['limits']}

    def configure(self, task_id, assignment_id, values):
        task, assigned = self.selected(task_id)
        if task['status'] != 'pending' or assigned['event_id'] != assignment_id:
            raise ValidationError('Task or worker selection changed; inspect it again')
        if not isinstance(values, dict):
            raise ValidationError('Configuration must be a JSON object')
        worker = assigned['worker_id']
        if worker == 'project-status':
            if values:
                raise ValidationError('Project status accepts no extra configuration')
        elif worker == 'research-collect':
            ResearchService(self.database).configure(task_id, **values)
        elif worker == 'research-synthesize':
            SynthesisService(self.database).configure(task_id, **values)
        else:
            options = dict(values)
            asset_id = options.pop('input_id', '')
            InputService(self.database).bind(task_id, asset_id, **options)
        return self.configuration(task_id)

    def preview(self, task_id):
        _, assigned = self.selected(task_id)
        worker_id = assigned['worker_id']
        with self.database.connect() as c:
            c.execute('BEGIN')
            task = Service(self.database)._get(c, 'tasks', task_id)
            if task['status'] != 'pending':
                raise ValidationError('Only a pending task can be proposed')
            data, fingerprint = proposal(c, self.database, task_id, worker_id, resolve(worker_id))
            dependency = DependencyService(self.database).explain(task_id, connection=c)
        return {'proposal':data, 'fingerprint':fingerprint, 'dependency':dependency,
                'restrictions':['One explicit execution action consumes one current approval.',
                                'Dependencies, exclusive execution claim and inference recovery gates remain enforced.',
                                'No downstream task starts automatically.']}

    def request(self, task_id, reason, expected_fingerprint):
        preview = self.preview(task_id)
        if preview['dependency']['classification'] != 'ready':
            raise ValidationError('Dependencies are not ready; inspect prerequisites first')
        return ApprovalService(self.database).request(task_id, preview['proposal']['worker_id'], reason,
                                                      expected_fingerprint=expected_fingerprint)

    def state(self, task_id):
        with self.database.connect() as c:
            task = Service(self.database)._get(c, 'tasks', task_id)
            assigned = binding(c, task['id'])
            approvals = [dict(r) for r in c.execute('SELECT id,worker_id,status,fingerprint,execution_id,created_at,decided_at FROM approvals WHERE task_id=? ORDER BY rowid DESC', (task['id'],))]
            events = [dict(r) for r in c.execute('SELECT type,timestamp,execution_id FROM events WHERE task_id=? ORDER BY rowid', (task['id'],))]
            active = bool(c.execute("SELECT 1 FROM executions WHERE status='running'").fetchone())
            inference = bool(c.execute('SELECT 1 FROM inference_claim').fetchone())
        result = {'assignment':assigned, 'configuration':None, 'configuration_error':None,
                  'approvals':approvals, 'events':events, 'can_execute':False, 'approved_id':None,
                  'execution_gate':'Assign a suitable worker and preview its operation.'}
        if assigned:
            try:
                result['configuration'] = self.configuration(task_id)
                preview = self.preview(task_id)
                current = next((a for a in approvals if a['status']=='approved' and a['execution_id'] is None
                                and a['worker_id']==assigned['worker_id'] and a['fingerprint']==preview['fingerprint']), None)
                if preview['dependency']['classification'] != 'ready':
                    result['execution_gate'] = 'Dependencies are not ready.'
                elif active:
                    result['execution_gate'] = 'Another execution owns the global execution claim.'
                elif inference and assigned['worker_id']=='research-synthesize':
                    result['execution_gate'] = 'Inference is busy or uncertain; recovery must be resolved separately.'
                elif current is None:
                    result['execution_gate'] = 'A current, unused explicit approval is required.'
                else:
                    result.update(can_execute=True, approved_id=current['id'], execution_gate='Approved operation is ready for an explicit Execute action.')
            except (ValueError, OSError) as exc:
                result['configuration_error'] = str(exc)
                result['execution_gate'] = str(exc)
        return result

    def execute(self, task_id):
        _, assigned = self.selected(task_id)
        return ExecutionService(self.database).execute(task_id, assigned['worker_id'])

    def artifact(self, execution_id):
        execution = ExecutionService(self.database).get(identifier(execution_id))
        with self.database.connect() as c:
            stopped = c.execute("SELECT phase FROM execution_ownership WHERE execution_id=?", (execution['id'],)).fetchone()
        if stopped is None or stopped['phase'] != 'stopped':
            raise ValidationError('Artifact is not ready; inspect the running execution')
        path = self.database.path.resolve().parent / 'artifacts' / (execution['id']+'.json')
        return json.loads(read_bounded(path,8*1024*1024))
