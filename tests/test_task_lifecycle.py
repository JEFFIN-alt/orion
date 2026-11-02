"""Control-room lifecycle through actual HTTP/SQLite services in disposable databases."""
import json
import os
import unittest
from dataclasses import replace
from urllib.error import HTTPError
from uuid import uuid4

import test_control_room
from test_groq import mock_collect, mock_groq_synthesize, ENV
from unittest.mock import patch
from orion.approvals import ApprovalService
from orion.dependencies import DependencyService
from orion.execution import ExecutionService
from orion.inputs import InputService
from orion.models import ValidationError
from orion.research import ResearchService
from orion.service import timestamp
from orion.task_lifecycle import TaskLifecycle
from orion.workers import REGISTRY


class TaskLifecycleTests(unittest.TestCase):
    setUp=test_control_room.ControlRoomTests.setUp
    close_server=test_control_room.ControlRoomTests.close_server
    get=test_control_room.ControlRoomTests.get
    post=test_control_room.ControlRoomTests.post

    def task(self):
        return self.post('/api/tasks',{'title':'Disposable lifecycle fixture','project_id':self.project['id']})

    def assign(self,task,worker='project-status'):
        return self.post('/api/task-assignment',{'id':task['id'],'worker_id':worker})

    def configure(self,task,assigned,values):
        return self.post('/api/task-configuration',{'id':task['id'],'assignment_id':assigned['event_id'],'configuration':values})

    def approve(self,task):
        preview=self.get('/api/task-preview?id='+task['id'])
        request=self.post('/api/task-approval',{'preview_token':preview['preview_token'],'reason':'Explicit fixture approval'})
        confirmation=self.post('/api/approval-confirmation',{'id':request['id'],'decision':'approved','reason':'Fixture reviewed'})
        self.post('/api/approval-decision',{'confirmation':confirmation['confirmation']})
        return request

    def test_catalog_describes_only_actual_workers_and_defaults(self):
        catalog=self.get('/api/worker-catalog')
        self.assertEqual({w['identifier'] for w in catalog},set(REGISTRY))
        self.assertEqual(next(w for w in catalog if w['identifier']=='project-status')['defaults'],{})
        self.assertIn('source_execution',next(w for w in catalog if w['identifier']=='research-synthesize')['defaults'])
        self.assertTrue(all('configuration_help' in w and 'availability' in w for w in catalog))

    def test_assignment_validated_and_persistent_without_migration(self):
        task=self.task()
        with self.assertRaises(HTTPError):self.assign(task,'made-up-agent')
        assigned=self.assign(task)
        self.assertEqual(self.assign(task)['event_id'],assigned['event_id'])
        self.assertEqual(self.get('/api/tasks')[-1]['worker'],'project-status')
        self.assertEqual(self.get('/api/task?id='+task['id'])['lifecycle']['assignment']['event_id'],assigned['event_id'])
        with self.db.connect() as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],9)

    def test_configuration_rejects_extra_fields_and_changed_assignment(self):
        task=self.task();assigned=self.assign(task)
        with self.assertRaises(HTTPError):self.configure(task,assigned,{'execute_shell':'forbidden'})
        with self.assertRaises(HTTPError):self.configure(task,{'event_id':str(uuid4())},{})
        self.assertEqual(self.configure(task,assigned,{}),{})

    def test_complete_project_status_lifecycle_and_duplicate_execution(self):
        task=self.task();assigned=self.assign(task);self.configure(task,assigned,{})
        request=self.approve(task)
        state=self.get('/api/task?id='+task['id'])['lifecycle']
        self.assertTrue(state['can_execute'])
        self.assertEqual(state['approved_id'],request['id'])
        run=self.post('/api/task-execute',{'id':task['id']},'fixture-one-execution')
        self.assertEqual(run['status'],'succeeded',run['error'])
        duplicate=self.post('/api/task-execute',{'id':task['id']},'fixture-one-execution')
        self.assertEqual(duplicate['id'],run['id'])
        detail=self.get('/api/task?id='+task['id'])
        self.assertEqual(len(detail['history']),1)
        self.assertEqual(detail['task']['status'],'completed')
        self.assertEqual(self.get('/api/approval?id='+request['id'])['execution_id'],run['id'])
        self.assertEqual(self.get('/api/artifact?id='+run['id'])['project']['id'],self.project['id'])
        with self.assertRaises(HTTPError):self.assign(task)

    def test_execute_requires_approval_and_request_identifier(self):
        task=self.task();self.assign(task)
        with self.assertRaises(HTTPError):self.post('/api/task-execute',{'id':task['id']})
        with self.assertRaises(HTTPError):self.post('/api/task-execute',{'id':task['id']},'not-approved')
        self.assertEqual(self.get('/api/task?id='+task['id'])['history'],[])

    def test_wrong_worker_cannot_be_proposed_even_through_cli_service(self):
        task=self.task();self.assign(task,'research-collect')
        with self.assertRaises(ValidationError):
            ApprovalService(self.db).request(task['id'],'project-status','Wrong worker')
        with self.assertRaises(ValidationError):
            ExecutionService(self.db).execute(task['id'],'project-status')

    def test_preview_changes_and_preview_replay_rejected(self):
        task=self.task();self.assign(task)
        preview=self.get('/api/task-preview?id='+task['id'])
        self.service.update('tasks',task['id'],description='Changed after preview')
        with self.assertRaises(HTTPError):self.post('/api/task-approval',{'preview_token':preview['preview_token'],'reason':'Old preview'})
        self.assertEqual(self.get('/api/task?id='+task['id'])['lifecycle']['approvals'],[])
        preview=self.get('/api/task-preview?id='+task['id'])
        self.post('/api/task-approval',{'preview_token':preview['preview_token'],'reason':'Fresh preview'})
        with self.assertRaises(HTTPError):self.post('/api/task-approval',{'preview_token':preview['preview_token'],'reason':'Duplicate preview'})

    def test_reassignment_invalidates_approval_even_after_switching_back(self):
        task=self.task();assigned=self.assign(task);request=self.approve(task)
        self.assign(task,'csv-profile');new_assignment=self.assign(task)
        self.assertNotEqual(assigned['event_id'],new_assignment['event_id'])
        self.assertFalse(self.get('/api/task?id='+task['id'])['lifecycle']['can_execute'])
        with self.assertRaises(HTTPError):self.post('/api/task-execute',{'id':task['id']},'old-approval')
        self.assertIsNone(ApprovalService(self.db).get(request['id'])['execution_id'])

    def test_dependencies_block_approval_request_and_execution(self):
        task=self.task();self.assign(task)
        prerequisite=self.service.create_task(self.project['id'],'Pending prerequisite')
        DependencyService(self.db).add(task['id'],prerequisite['id'])
        preview=self.get('/api/task-preview?id='+task['id'])
        self.assertEqual(preview['dependency']['classification'],'waiting')
        with self.assertRaises(HTTPError):self.post('/api/task-approval',{'preview_token':preview['preview_token'],'reason':'Not ready'})
        with self.assertRaises(HTTPError):self.post('/api/task-execute',{'id':task['id']},'blocked-by-dependency')

    def test_csv_registered_input_configuration_and_independent_output(self):
        source=self.root/'fixture.csv';source.write_text('a,b\n1,2\n',encoding='utf-8')
        asset=InputService(self.db).import_csv(source)
        self.assertEqual(self.get('/api/inputs')[0]['id'],asset['id'])
        task=self.task();assigned=self.assign(task,'csv-profile')
        with self.assertRaises(HTTPError):self.configure(task,assigned,{'input_id':'C:/arbitrary.csv'})
        self.configure(task,assigned,{'input_id':asset['id'],'max_rows':5})
        self.approve(task)
        run=self.post('/api/task-execute',{'id':task['id']},'csv-fixture')
        self.assertEqual(run['status'],'succeeded',run['error'])
        self.assertEqual(run['latest_verification']['status'],'passed')
        self.assertEqual(self.get('/api/artifact?id='+run['id'])['row_count'],1)

    def test_research_configuration_uses_original_validator(self):
        task=self.task();assigned=self.assign(task,'research-collect')
        with self.assertRaises(HTTPError):self.configure(task,assigned,{'question':'Fixture','url':'https://arbitrary.invalid'})
        self.configure(task,assigned,{'question':'Fixture research','providers':['github'],'github_limit':2})
        preview=self.get('/api/task-preview?id='+task['id'])
        self.assertEqual(preview['proposal']['research']['configuration']['question'],'Fixture research')
        self.assertEqual(preview['proposal']['worker_id'],'research-collect')

    def test_synthesis_source_configuration_and_uncertain_inference_gate(self):
        source_task=self.service.create_task(self.project['id'],'Mock upstream research')
        ResearchService(self.db).configure(source_task['id'],'Fixture question',include_readme=False)
        collector=ExecutionService(self.db,registry={'research-collect':replace(REGISTRY['research-collect'],handler=mock_collect)})
        upstream=collector.execute(source_task['id'],'research-collect')
        self.assertEqual(upstream['status'],'succeeded')
        task=self.task();assigned=self.assign(task,'research-synthesize')
        with self.assertRaises(HTTPError):self.configure(task,assigned,{'source_execution':str(uuid4())})
        self.configure(task,assigned,{'source_execution':upstream['id']})
        preview=self.get('/api/task-preview?id='+task['id'])
        self.assertEqual(preview['proposal']['synthesis']['source_execution'],upstream['id'])
        request=self.approve(task)
        with self.db.connect(write=True) as c:
            c.execute('INSERT INTO inference_claim VALUES (1,?,?,?,1)',('fixture-uncertain',os.getpid(),timestamp()))
        detail=self.get('/api/task?id='+task['id'])
        self.assertFalse(detail['lifecycle']['can_execute'])
        with self.assertRaises(HTTPError):self.post('/api/task-execute',{'id':task['id']},'uncertain-gate')
        self.assertIsNone(ApprovalService(self.db).get(request['id'])['execution_id'])

    def test_artifact_endpoint_rejects_arbitrary_paths_and_missing_records(self):
        for value in ('../../secret','',str(uuid4())):
            with self.assertRaises(HTTPError):self.get('/api/artifact?id='+value)

    def test_assigned_synthesis_uses_original_independent_verifier_offline(self):
        source_task=self.service.create_task(self.project['id'],'Mock source for assigned synthesis')
        ResearchService(self.db).configure(source_task['id'],'Fixture question',include_readme=False)
        collector=ExecutionService(self.db,registry={'research-collect':replace(REGISTRY['research-collect'],handler=mock_collect)})
        upstream=collector.execute(source_task['id'],'research-collect')
        with patch.dict(os.environ,ENV):
            task=self.task();assigned=self.assign(task,'research-synthesize')
            self.configure(task,assigned,{'source_execution':upstream['id']})
            self.approve(task)
            engine=ExecutionService(self.db,registry={'research-synthesize':replace(REGISTRY['research-synthesize'],handler=mock_groq_synthesize)})
            run=engine.execute(task['id'],'research-synthesize')
        self.assertEqual(run['status'],'succeeded',run['error'])
        self.assertEqual(run['latest_verification']['status'],'passed')
        self.assertEqual(self.get('/api/evidence?id='+run['id'])['operation']['source_execution'],upstream['id'])

    def test_gets_do_not_assign_or_create_approvals(self):
        task=self.task()
        self.get('/api/task?id='+task['id']);self.get('/api/worker-catalog')
        state=self.get('/api/task?id='+task['id'])['lifecycle']
        self.assertIsNone(state['assignment'])
        self.assertEqual(state['approvals'],[])
