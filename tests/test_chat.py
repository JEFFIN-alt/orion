import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import test_foundation
from orion.provider import AIConfig,ProviderError,Response
from orion.ollama import OllamaProvider
from orion.conversations import ConversationService
from orion.plans import PlanService
from orion.plan_schema import validate_plan,fingerprint
from orion.context import build_context
from orion.models import ValidationError
from orion.web_chat import make_server
from orion.execution import ExecutionService

PLAN={"title":"Test project","description":"A proposed fixture", "assumptions":["Local only"],"risks":["Requirements may change"],"unresolved_questions":[],"tasks":[{"key":"a","title":"Implement","description":"Build a small utility","priority":50,"dependencies":[],"acceptance_criteria":["Unit tests pass"]}]}

class FakeProvider:
    config=AIConfig()
    def __init__(self,content="Fixture response",error=None): self.content,self.error=content,error
    def availability(self): return {"available":False,"model":"test-fixture","message":"Test provider only"}
    def chat(self,messages,schema=None):
        if self.error: raise self.error
        return Response(self.content,"test-fixture","fake",0.01)


class ChatTests(unittest.TestCase):
    def setUp(self):
        test_foundation.FoundationTests.setUp(self)
        self.provider=FakeProvider()
        self.chat=ConversationService(self.db,self.provider)
        self.conversation=self.chat.create("CEO fixture",self.project["id"])
        self.plans=PlanService(self.db)

    def proposal(self):
        self.provider.content=json.dumps(PLAN)
        return self.chat.send(self.conversation["id"],"Plan a utility",True)["plan"]

    def test_configuration(self):
        for endpoint in ("http://example.com","http://127.0.0.1/other","https://127.0.0.1","http://user:pass@localhost"):
            with self.assertRaises(ValidationError): AIConfig(endpoint=endpoint)
        with self.assertRaises(ValidationError): AIConfig(context=100)
        with patch.dict(os.environ,{"ORION_AI_CONTEXT":"4096","ORION_AI_MODEL":"local-test"}):
            self.assertEqual(AIConfig.load().model,"local-test")

    def test_persistence_fresh_process_and_labels(self):
        cid=self.conversation["id"]
        self.chat.send(cid,"Hello")
        messages=self.chat.messages(cid)
        self.assertEqual([m["kind"] for m in messages],["user","model"])
        script="from pathlib import Path; import sys,json; from orion.database import Database; from orion.conversations import ConversationService; from orion.ollama import OllamaProvider; from orion.provider import AIConfig; print(json.dumps(ConversationService(Database(Path(sys.argv[1])),OllamaProvider(AIConfig())).messages(sys.argv[2])))"
        result=subprocess.run([sys.executable,"-c",script,str(self.db.path),cid],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)[1]["model"],"test-fixture")

    def test_unavailable_is_system_error(self):
        self.provider.error=ProviderError("Service unavailable")
        result=self.chat.send(self.conversation["id"],"Hello")
        self.assertFalse(result["model_response"])
        self.assertEqual(self.chat.messages(self.conversation["id"])[-1]["kind"],"error")
        self.assertEqual(self.chat.messages(self.conversation["id"])[-1]["role"],"system")

    def test_uncertain_timeout_blocks_overlap(self):
        self.provider.error=ProviderError("Timeout",uncertain=True)
        self.chat.send(self.conversation["id"],"Hello")
        with self.assertRaises(ValidationError): self.chat.send(self.conversation["id"],"Again")
        self.chat.reset_claim("Test service restarted")
        self.assertIsNone(self.chat.status()["inference_claim"])

    def test_bounded_context(self):
        history=[{"kind":"model","role":"assistant","content":"x"*1000} for _ in range(200)]
        history.append({"kind":"user","role":"user","content":"Latest"})
        output=build_context(history,{"project":None},4096)
        self.assertLessEqual(sum(len(m["content"].encode()) for m in output),8192)
        self.assertEqual(output[-1]["content"],"Latest")

    def test_plan_validation(self):
        validate_plan(PLAN)
        for key,value in (("tasks",[]),("title",""),("unexpected",True)):
            body=json.loads(json.dumps(PLAN));body[key]=value
            with self.assertRaises(ValidationError): validate_plan(body)
        body=json.loads(json.dumps(PLAN));body["tasks"][0]["dependencies"]=["a"]
        with self.assertRaises(ValidationError): validate_plan(body)

    def test_invalid_plan_retains_conversation_no_project(self):
        self.provider.content="not json"
        before=len(self.service.list("projects"))
        result=self.chat.send(self.conversation["id"],"Plan",True)
        self.assertIn("plan_error",result)
        self.assertEqual(len(self.service.list("projects")),before)
        self.assertEqual(len(self.chat.messages(self.conversation["id"])),3)

    def test_approve_atomic_creation_and_duplicate(self):
        before=len(self.service.list("projects"));plan=self.proposal()
        self.assertEqual(len(self.service.list("projects")),before)
        result=self.plans.decide(plan["id"],"approved",plan["fingerprint"],"Fixture approval")
        self.assertEqual(len(self.service.list("projects")),before+1)
        tasks=self.service.list("tasks",result["project_id"])
        self.assertEqual(len(tasks),1)
        with self.assertRaises(ValidationError): ExecutionService(self.db).execute(tasks[0]["id"],"project-status")
        with self.assertRaises(ValidationError): self.plans.decide(plan["id"],"approved",plan["fingerprint"],"Duplicate")

    def test_rejection_and_modified_plan(self):
        plan=self.proposal();before=len(self.service.list("projects"))
        with self.assertRaises(ValidationError): self.plans.decide(plan["id"],"approved","changed","Review")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect(write=True) as c: c.execute("UPDATE plans SET body_json='{}' WHERE id=?",(plan["id"],))
        self.plans.decide(plan["id"],"rejected",plan["fingerprint"],"Not ready")
        self.assertEqual(len(self.service.list("projects")),before)
        self.assertEqual(self.plans.get(plan["id"])["status"],"rejected")

    def test_ui_missing_model_and_origin(self):
        self.provider.error=ProviderError("Model missing")
        server=make_server(self.db,self.provider.config,0,self.provider)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f"http://127.0.0.1:{server.server_port}"
        try:
            html=urlopen(base).read().decode();token=re.search("const token='([^']+)'",html)[1]
            self.assertIn("Propose plan",html)
            data=json.dumps({"id":self.conversation["id"],"text":"Hello"}).encode()
            with self.assertRaises(HTTPError): urlopen(Request(base+"/api/message",data=data))
            request=Request(base+"/api/message",data=data,headers={"Origin":base,"X-Orion-Token":token,"Content-Type":"application/json"})
            result=json.load(urlopen(request));self.assertEqual(result["error"],"Model missing")
        finally: server.shutdown();server.server_close();thread.join()

    def test_migration_preserves_all_previous_tables(self):
        # Build a populated schema-4 fixture from the actual migration definitions.
        from orion.database import Database,SCHEMA,MIGRATION_2,MIGRATION_3,MIGRATION_4
        old=Database(self.root/'old.sqlite3')
        with old.connect(write=True) as c:
            for sql in (*SCHEMA,*MIGRATION_2,*MIGRATION_3,*MIGRATION_4): c.execute(sql)
            c.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)",tuple(self.project.values()))
            c.execute("PRAGMA user_version=4")
            names=[row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            before={name:[tuple(row) for row in c.execute('SELECT * FROM '+name)] for name in names}
        old.initialize();old.initialize()
        with old.connect() as c:
            for name in names: self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM '+name)],before[name])
        self.assertEqual(old.health()['schema_version'],7)


class OllamaHttpTests(unittest.TestCase):
    def test_adapter_real_http_fixture(self):
        class Handler(BaseHTTPRequestHandler):
            mode="good"
            def log_message(self,*args): pass
            def do_GET(self):
                body=json.dumps({"models":[{"name":"fixture"}]}).encode();self.send_response(200);self.end_headers();self.wfile.write(body)
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.server.payload=payload
                if self.mode=='slow': time.sleep(.2)
                self.send_response(200);self.end_headers()
                try: self.wfile.write(b'invalid' if self.mode=='bad' else json.dumps({"done":True,"model":"fixture","message":{"role":"assistant","content":"Fixture HTTP response"}}).encode())
                except OSError: pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            provider=OllamaProvider(AIConfig(endpoint=f'http://127.0.0.1:{server.server_port}',model='fixture',timeout=1))
            self.assertTrue(provider.availability()['available'])
            self.assertEqual(provider.chat([{'role':'user','content':'Hi'}]).content,'Fixture HTTP response')
            self.assertEqual(server.payload['options']['num_ctx'],4096)
            Handler.mode='bad'
            with self.assertRaises(ProviderError): provider.chat([])
            Handler.mode='slow'
            provider=OllamaProvider(replace(provider.config,timeout=.05))
            with self.assertRaises(ProviderError): provider.chat([])
        finally: server.shutdown();server.server_close();thread.join()
        self.assertFalse(provider.availability()['available'])
