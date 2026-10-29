import json
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from uuid import uuid4
from pathlib import Path
import test_foundation
from orion.dependencies import DependencyService
from orion.execution import ExecutionService
from orion.models import ValidationError
from orion.approvals import ApprovalService
from orion.inputs import InputService
from orion.verification import VerificationService
from orion.database import Database,SCHEMA,MIGRATION_2,MIGRATION_3,MIGRATION_4,MIGRATION_5


class DependencyTests(unittest.TestCase):
    cli = test_foundation.FoundationTests.cli
    def setUp(self):
        test_foundation.FoundationTests.setUp(self)
        self.deps=DependencyService(self.db)
        self.engine=ExecutionService(self.db)
        self.a=self.service.create_task(self.project["id"],"A")
        self.b=self.service.create_task(self.project["id"],"B")
        self.c=self.service.create_task(self.project["id"],"C")

    def chain(self):
        self.deps.add(self.b["id"],self.a["id"])
        self.deps.add(self.c["id"],self.b["id"])

    def state(self,task): return self.deps.explain(task["id"])["classification"]

    def test_constraints(self):
        self.chain()
        other=self.service.create_project("Other")
        foreign=self.service.create_task(other["id"],"Foreign")
        for left,right in ((self.a,self.a),(self.b,self.a),(self.a,self.c),(self.a,foreign),(self.a,{"id":str(uuid4())})):
            with self.assertRaises(ValidationError): self.deps.add(left["id"],right["id"])
        self.assertEqual(len(self.deps.project(self.project["id"])["dependencies"]),2)

    def test_queue_progression_and_direct_enforcement(self):
        self.chain()
        self.assertEqual([self.state(t) for t in (self.a,self.b,self.c)],["ready","waiting","waiting"])
        with self.assertRaises(ValidationError): self.engine.execute(self.b["id"],"project-status")
        self.assertEqual(self.engine.history(self.b["id"]),[])
        self.assertEqual(self.engine.execute(self.a["id"],"project-status")["status"],"succeeded")
        self.assertEqual(self.state(self.b),"ready")
        self.assertEqual(self.engine.execute(self.b["id"],"project-status")["status"],"succeeded")
        self.assertEqual(self.state(self.c),"ready")

    def test_manual_complete_failure_cancel_and_transitive_block(self):
        self.chain()
        self.service.transition("tasks",self.a["id"],"in_progress")
        self.service.transition("tasks",self.a["id"],"completed")
        self.assertEqual(self.state(self.b),"blocked")
        self.assertEqual(self.state(self.c),"blocked")
        self.assertIn("manual completion",self.deps.explain(self.a["id"])["reason"])
        for state in ("failed","cancelled","blocked"):
            with self.db.connect(write=True) as c: c.execute("UPDATE tasks SET status=? WHERE id=?",(state,self.a["id"]))
            self.assertEqual(self.state(self.b),"blocked")

    def test_latest_attempt_overrides_old_success(self):
        self.chain();self.engine.execute(self.a["id"],"project-status")
        with self.db.connect(write=True) as c:
            c.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)",(str(uuid4()),self.a["id"],"project-status","failed","later","later",2,None,None,"fixture failure"))
        self.assertEqual(self.state(self.b),"blocked")
        self.assertEqual(len(self.engine.history(self.a["id"])),2)

    def test_required_verification_missing_failed_wrong_digest(self):
        self.chain()
        source=self.root/'input.csv';source.write_text('x\n1\n')
        asset=InputService(self.db).import_csv(source)
        InputService(self.db).bind(self.a["id"],asset["id"])
        result=self.engine.execute(self.a["id"],"csv-profile")
        self.assertEqual(self.state(self.b),"ready")
        with self.db.connect(write=True) as c:
            c.execute("INSERT INTO verifications VALUES (?,?,?,?,?,?,?,?,?,?)", (str(uuid4()),result['id'],'csv-independent','1','passed','wrong','wrong','later','[]','Fixture mismatched binding'))
        self.assertEqual(self.state(self.b),'blocked')
        VerificationService(self.db).verify(result['id'])
        self.assertEqual(self.state(self.b),'ready')
        Path(result["result"]["artifact"]).write_text('{}')
        VerificationService(self.db).verify(result["id"])
        self.assertEqual(self.state(self.b),"blocked")
        with self.assertRaises(ValidationError): self.engine.execute(self.b["id"],"project-status")
        # Missing verification for a separate CSV attempt, with no history deletion.
        with self.db.connect(write=True) as c:
            c.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)",(str(uuid4()),self.a["id"],"csv-profile","succeeded","later","later",2,None,None,None))
        self.assertEqual(self.state(self.b),"blocked")

    def test_ready_still_needs_approval_and_graph_change_invalidates(self):
        approvals=ApprovalService(self.db)
        request=approvals.request(self.b["id"],"project-status","Review")
        approvals.decide(request["id"],"approved","Yes")
        self.deps.add(self.b["id"],self.a["id"])
        with self.assertRaises(ValidationError): self.engine.execute(self.b["id"],"project-status")
        self.engine.execute(self.a["id"],"project-status")
        with self.assertRaises(ValidationError): self.engine.execute(self.b["id"],"project-status")
        fresh=approvals.request(self.b["id"],"project-status","New review")
        approvals.decide(fresh["id"],"approved","Yes")
        self.assertEqual(self.engine.execute(self.b["id"],"project-status")["status"],"succeeded")

    def test_inspection_read_only_and_restart(self):
        self.chain()
        with self.db.connect() as c:
            before={name:[tuple(r) for r in c.execute('SELECT * FROM '+name)] for name in ('tasks','executions','events')}
        output=self.cli('queue','list',self.project['id'],'--state','waiting')
        self.assertEqual(output.returncode,0,output.stderr)
        self.assertEqual(len(json.loads(output.stdout)['tasks']),2)
        self.assertEqual(self.cli('dependencies','show',self.b['id']).returncode,0)
        self.assertEqual(self.cli('queue','explain','bad').returncode,1)
        with self.db.connect() as c:
            for name,rows in before.items(): self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM '+name)],rows)

    def test_plan_mapping_and_rollback(self):
        from test_chat import FakeProvider, PLAN
        from orion.conversations import ConversationService
        from orion.plans import PlanService
        body=json.loads(json.dumps(PLAN))
        body['tasks'] += [{**body['tasks'][0], 'key':'b','dependencies':['a']},{**body['tasks'][0],'key':'c','dependencies':['a','b']}]
        chat=ConversationService(self.db,FakeProvider(json.dumps(body)))
        conversation=chat.create('Fixture dependency plan')
        proposal=chat.send(conversation['id'],'Plan',True)['plan']
        # Force a genuine database failure in the final dependency registration.
        with self.db.connect(write=True) as c:
            c.execute("CREATE TRIGGER fail_dependency BEFORE INSERT ON task_dependencies BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        before=len(self.service.list('projects'))
        with self.assertRaises(ValidationError): PlanService(self.db).decide(proposal['id'],'approved',proposal['fingerprint'],'Review')
        self.assertEqual(len(self.service.list('projects')),before)
        self.assertEqual(PlanService(self.db).get(proposal['id'])['status'],'proposed')
        with self.db.connect(write=True) as c: c.execute('DROP TRIGGER fail_dependency')
        applied=PlanService(self.db).decide(proposal['id'],'approved',proposal['fingerprint'],'Review')
        edges={(e['task_id'],e['prerequisite_id']) for e in self.deps.project(applied['project_id'])['dependencies']}
        ids=applied['task_ids']
        self.assertEqual(edges,{(ids['b'],ids['a']),(ids['c'],ids['a']),(ids['c'],ids['b'])})

    def test_transaction_sees_committed_invalidation(self):
        self.chain();self.engine.execute(self.a['id'],'project-status')
        # A competing writer commits invalid state before the execution claim can lock.
        connection=sqlite3.connect(self.db.path)
        connection.execute('BEGIN IMMEDIATE')
        connection.execute("UPDATE tasks SET status='failed' WHERE id=?",(self.a['id'],))
        outcome=[]
        def attempt():
            try: self.engine.execute(self.b['id'],'project-status')
            except ValidationError as exc: outcome.append(str(exc))
        thread=threading.Thread(target=attempt);thread.start();time.sleep(.1)
        connection.commit();connection.close();thread.join(10)
        self.assertFalse(thread.is_alive());self.assertTrue(outcome)
        self.assertEqual(self.engine.history(self.b['id']),[])

    def test_migration_preserves_schema5(self):
        old=Database(self.root/'old.sqlite3')
        with old.connect(write=True) as c:
            for sql in (*SCHEMA,*MIGRATION_2,*MIGRATION_3,*MIGRATION_4,*MIGRATION_5): c.execute(sql)
            c.execute('INSERT INTO projects VALUES (?,?,?,?,?,?)',tuple(self.project.values()))
            c.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)',tuple(self.a.values()))
            c.execute('PRAGMA user_version=5')
        old.initialize();old.initialize()
        self.assertEqual(DependencyService(old).explain(self.a['id'])['classification'],'ready')
        self.assertEqual(old.health()['schema_version'],7)

    def test_invalidation_after_claim_cannot_record_success(self):
        from orion.workers import REGISTRY
        from dataclasses import replace
        self.chain()
        self.engine.execute(self.a['id'],'project-status')
        worker = REGISTRY['project-status']
        def invalidate(snapshot, output):
            worker.validator(snapshot, output)
            with self.db.connect(write=True) as c:
                c.execute("UPDATE tasks SET status='failed' WHERE id=?", (self.a['id'],))
        engine = ExecutionService(self.db, registry={'project-status':replace(worker,validator=invalidate)})
        result = engine.execute(self.b['id'],'project-status')
        self.assertEqual(result['status'],'failed')
        self.assertIn('Prerequisite evidence changed',result['error'])
        self.assertEqual(self.state(self.c),'blocked')

    def test_database_constraints_cannot_be_bypassed_by_insert(self):
        self.chain()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect(write=True) as c:
                c.execute('INSERT INTO task_dependencies VALUES (?,?,?)',(self.a['id'],self.c['id'],'now'))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect(write=True) as c:
                c.execute('INSERT INTO task_dependencies VALUES (?,?,?)',(self.a['id'],str(uuid4()),'now'))

    def test_invalid_plan_graph_and_revised_plan_approval(self):
        from test_chat import PLAN, FakeProvider
        from orion.plans import validate_plan, PlanService
        from orion.conversations import ConversationService
        body=json.loads(json.dumps(PLAN))
        body['tasks'].append({**body['tasks'][0],'key':'b','dependencies':['a']})
        body['tasks'][0]['dependencies']=['b']
        with self.assertRaises(ValidationError): validate_plan(body)
        body['tasks'][0]['dependencies']=['missing']
        with self.assertRaises(ValidationError): validate_plan(body)
        provider=FakeProvider(json.dumps(PLAN))
        chat=ConversationService(self.db,provider)
        conversation=chat.create('Revised plan fixture')
        first=chat.send(conversation['id'],'Plan',True)['plan']
        revised=json.loads(json.dumps(PLAN));revised['title']='Revised title'
        provider.content=json.dumps(revised)
        second=chat.send(conversation['id'],'Revise',True)['plan']
        plans=PlanService(self.db)
        with self.assertRaises(ValidationError):
            plans.decide(second['id'],'approved',first['fingerprint'],'Old review')
        applied=plans.decide(second['id'],'approved',second['fingerprint'],'Fresh review')
        self.assertEqual(self.deps.project(applied['project_id'])['dependencies'],[])
