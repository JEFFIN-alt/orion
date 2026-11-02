"""Actual local web routes backed by isolated SQLite records and fixture providers."""
import hashlib
import json
import os
import re
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from uuid import uuid4

import test_foundation
from test_chat import FakeProvider
from test_groq import mock_collect
from orion.approvals import ApprovalService
from orion.execution import ExecutionService
from orion.research import ResearchService
from orion.web_chat import make_server
from orion.workers import REGISTRY


class ControlRoomTests(unittest.TestCase):
    def setUp(self):
        test_foundation.FoundationTests.setUp(self)
        self.provider=FakeProvider()
        self.server=make_server(self.db,self.provider.config,0,self.provider)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.01},daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.html=urlopen(self.base).read().decode()
        self.token=re.search("const token='([^']+)'",self.html)[1]

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def get(self,path):
        return json.load(urlopen(self.base+path))

    def post(self,path,body,request_id=None,authorized=True):
        headers={'Content-Type':'application/json'}
        if authorized:headers.update({'Origin':self.base,'X-Orion-Token':self.token})
        if request_id:headers['X-Orion-Request']=request_id
        return json.load(urlopen(Request(self.base+path,data=json.dumps(body).encode(),headers=headers)))

    def request_approval(self):
        task=self.service.create_task(self.project['id'],'Approval fixture',require_approval=True)
        request=ApprovalService(self.db).request(task['id'],'project-status','Offline test')
        return task,request

    def test_dashboard_and_static_assets(self):
        data=self.get('/api/overview')
        self.assertEqual(data['counts']['projects'],1)
        self.assertEqual(data['counts']['tasks'],0)
        self.assertEqual(data['recent_executions'],[])
        self.assertEqual(data['provider_reachability'],'Not checked')
        self.assertIn('Company Control Room',self.html)
        css=urlopen(self.base+'/control-room.css')
        self.assertIn('text/css',css.headers['Content-Type'])
        self.assertIn(b'@media',css.read())
        script=urlopen(self.base+'/control-room.js').read().decode()
        for page in ('dashboard','chat','projects','tasks','workers','approvals','research','executions','settings'):
            self.assertIn(page,script)

    def test_project_task_creation_and_inspection(self):
        project=self.post('/api/projects',{'name':'Web project','description':'Created through API'})
        task=self.post('/api/tasks',{'project_id':project['id'],'title':'Web task','priority':7})
        tasks=self.get('/api/tasks?project='+project['id'])
        self.assertEqual(tasks[0]['id'],task['id'])
        self.assertIsNone(tasks[0]['worker'])
        detail=self.get('/api/task?id='+task['id'])
        self.assertTrue(detail['dependency']['approval_required'])
        self.assertEqual(detail['dependency']['classification'],'ready')
        p=next(p for p in self.get('/api/projects') if p['id']==project['id'])
        self.assertEqual((p['task_count'],p['completed_count']),(1,0))

    def test_project_duplicate_submission_returns_original(self):
        first=self.post('/api/projects',{'name':'One project'},'one-request')
        second=self.post('/api/projects',{'name':'One project'},'one-request')
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(self.service.list('projects')),2)
        with self.assertRaises(HTTPError) as raised:
            self.post('/api/projects',{'name':'Changed'},'one-request')
        self.assertEqual(raised.exception.code,409)

    def test_conversation_real_service_integration_with_fixture_provider(self):
        c=self.post('/api/conversations',{'title':'Fixture conversation','project_id':self.project['id']})
        result=self.post('/api/message',{'id':c['id'],'text':'Fixture message'})
        self.assertIn('message_id',result)
        data=self.get('/api/conversation?id='+c['id'])
        self.assertEqual([m['kind'] for m in data['messages']],['user','model'])
        self.assertEqual(data['context']['project']['id'],self.project['id'])

    def test_approval_requires_confirmation_and_normal_service_decision(self):
        task,request=self.request_approval()
        detail=self.get('/api/approval?id='+request['id'])
        self.assertTrue(detail['can_decide'])
        self.assertEqual(detail['proposal']['task_id'],task['id'])
        with self.assertRaises(HTTPError):
            self.post('/api/approval-decision',{'confirmation':'invented'})
        confirmation=self.post('/api/approval-confirmation',{'id':request['id'],'decision':'approved','reason':'Reviewed fixture'})
        result=self.post('/api/approval-decision',{'confirmation':confirmation['confirmation']})
        self.assertEqual(result['status'],'approved')
        self.assertIsNone(result['execution_id'])
        with self.assertRaises(HTTPError):
            self.post('/api/approval-decision',{'confirmation':confirmation['confirmation']})

    def test_stale_confirmation_rejected_atomically(self):
        task,request=self.request_approval()
        confirmation=self.post('/api/approval-confirmation',{'id':request['id'],'decision':'approved','reason':'Review'})
        self.service.update('tasks',task['id'],description='Material change')
        with self.assertRaises(HTTPError):
            self.post('/api/approval-decision',{'confirmation':confirmation['confirmation']})
        self.assertEqual(ApprovalService(self.db).get(request['id'])['status'],'pending')
        self.assertFalse(self.get('/api/approval?id='+request['id'])['can_decide'])

    def test_rejection_and_consumed_request_readonly(self):
        task,request=self.request_approval()
        c=self.post('/api/approval-confirmation',{'id':request['id'],'decision':'rejected','reason':'Decline'})
        self.post('/api/approval-decision',{'confirmation':c['confirmation']})
        self.assertEqual(ApprovalService(self.db).get(request['id'])['status'],'rejected')
        task,request=self.request_approval()
        ApprovalService(self.db).decide(request['id'],'approved','Fixture')
        run=ExecutionService(self.db).execute(task['id'],'project-status')
        detail=self.get('/api/approval?id='+request['id'])
        self.assertEqual(detail['eligibility'],'Consumed')
        self.assertFalse(detail['can_decide'])
        self.assertEqual(detail['execution_id'],run['id'])

    def test_executions_and_worker_registry(self):
        task=self.service.create_task(self.project['id'],'Local status fixture')
        run=ExecutionService(self.db).execute(task['id'],'project-status')
        self.assertEqual(self.get('/api/executions')[0]['id'],run['id'])
        detail=self.get('/api/execution?id='+run['id'])
        self.assertEqual(detail['status'],'succeeded')
        self.assertEqual(detail['verifications'],[])
        self.assertEqual({w['identifier'] for w in self.get('/api/workers')},set(REGISTRY))

    def test_research_packet_and_readonly_gets(self):
        task=self.service.create_task(self.project['id'],'Mock source capture')
        ResearchService(self.db).configure(task['id'],'Fixture question',include_readme=False)
        engine=ExecutionService(self.db,registry={'research-collect':replace(REGISTRY['research-collect'],handler=mock_collect)})
        run=engine.execute(task['id'],'research-collect')
        self.assertEqual(run['status'],'succeeded',run['error'])
        before=hashlib.sha256(self.db.path.read_bytes()).hexdigest()
        evidence=self.get('/api/evidence?id='+run['id'])
        self.assertEqual(len(evidence['packet']['records']),2)
        self.assertEqual(evidence['verifications'][0]['status'],'passed')
        self.assertEqual(self.get('/api/research')['collections'][0]['configuration']['question'],'Fixture question')
        self.get('/api/overview');self.get('/api/tasks');self.get('/api/task?id='+task['id'])
        self.assertEqual(hashlib.sha256(self.db.path.read_bytes()).hexdigest(),before)

    def test_origin_token_and_host_enforcement(self):
        with self.assertRaises(HTTPError) as raised:
            self.post('/api/projects',{'name':'Forbidden'},authorized=False)
        self.assertEqual(raised.exception.code,403)
        with self.assertRaises(HTTPError):
            urlopen(Request(self.base+'/api/overview',headers={'Host':'evil.invalid'}))
        with self.assertRaises(HTTPError):
            urlopen(Request(self.base+'/api/projects',data=b'{}',headers={'Host':self.base.split('//')[1],'Origin':'https://evil.invalid','X-Orion-Token':self.token}))

    def test_missing_records_and_input_errors(self):
        for path in ('/api/task?id=','/api/task?id='+str(uuid4()),'/api/approval?id='+str(uuid4()),'/api/execution?id='+str(uuid4())):
            with self.assertRaises(HTTPError): self.get(path)
        for body in ({'name':''},{'name':'valid','shell':'forbidden'}):
            with self.assertRaises(HTTPError): self.post('/api/projects',body)
        with self.assertRaises(HTTPError):
            self.post('/api/tasks',{'project_id':self.project['id'],'title':'Invalid','priority':True})

    def test_credential_isolation_and_error_redaction(self):
        secret='synthetic-ui-credential'
        self.service.update('projects',self.project['id'],description=secret)
        with patch.dict(os.environ,{'ORION_GROQ_API_KEY':secret}):
            projects=json.dumps(self.get('/api/projects'))
            self.assertNotIn(secret,projects)
            self.assertIn('[redacted]',projects)
            self.assertNotIn(secret,json.dumps(self.get('/api/overview')))

    def test_confirmation_expiration(self):
        _,request=self.request_approval()
        c=self.post('/api/approval-confirmation',{'id':request['id'],'decision':'approved','reason':'Review'})
        with patch('orion.web_chat.time.monotonic',return_value=10**12):
            with self.assertRaises(HTTPError):
                self.post('/api/approval-decision',{'confirmation':c['confirmation']})
