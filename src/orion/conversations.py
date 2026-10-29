"""Persistent chat with a database-wide single-inference claim."""
import os
import json
from uuid import uuid4
from .models import ValidationError, NotFoundError, required
from .service import identifier, timestamp, Service
from .provider import Provider, ProviderError
from .context import project_context, build_context
from .plan_schema import PLAN_SCHEMA, parse_plan
from .plans import PlanService, audit


class ConversationService:
    def __init__(self,database,provider: Provider):
        self.database,self.provider=database,provider

    def create(self,title="New conversation",project_id=None):
        title=required(title,"title")[:120]; cid=str(uuid4()); now=timestamp()
        with self.database.connect(write=True) as c:
            if project_id: Service(self.database)._get(c,"projects",project_id)
            c.execute("INSERT INTO conversations VALUES (?,?,?,?,?)",(cid,title,project_id,now,now))
            audit(c,cid,"conversation_created")
        return self.get(cid)

    def get(self,cid):
        with self.database.connect() as c:
            row=c.execute("SELECT * FROM conversations WHERE id=?",(identifier(cid),)).fetchone()
            if row is None: raise NotFoundError("Conversation not found")
            return dict(row)

    def list(self):
        with self.database.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 100")]

    def projects(self):
        with self.database.connect() as c:
            return [dict(r) for r in c.execute("SELECT id,name,status FROM projects ORDER BY created_at DESC LIMIT 100")]

    def messages(self,cid):
        self.get(cid)
        with self.database.connect() as c:
            return list(reversed([dict(r) for r in c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid DESC LIMIT 100",(identifier(cid),))]))

    def context(self,cid): return project_context(self.database,self.get(cid)["project_id"])

    def _message(self,cid,role,kind,content,response=None):
        mid=str(uuid4())
        with self.database.connect(write=True) as c:
            c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",(mid,cid,role,kind,content,response.provider if response else None,response.model if response else None,response.elapsed_seconds if response else None,timestamp()))
            c.execute("UPDATE conversations SET updated_at=? WHERE id=?",(timestamp(),cid))
        return mid

    def send(self,cid,text,planning=False):
        cid=self.get(cid)["id"]; text=required(text,"message")
        if len(text.encode())>2000: raise ValidationError("Message exceeds 2000 UTF-8 bytes; split it into shorter messages")
        token=str(uuid4())
        with self.database.connect(write=True) as c:
            if c.execute("SELECT 1 FROM inference_claim").fetchone(): raise ValidationError("Inference is busy or unresolved. Inspect ai-status; do not overlap requests")
            c.execute("INSERT INTO inference_claim VALUES (1,?,?,?,0)",(token,os.getpid(),timestamp()))
        uncertain=False
        try:
            self._message(cid,"user","user",text)
            messages=build_context(self.messages(cid),self.context(cid),self.provider.config.context,planning)
            response=self.provider.chat(messages,PLAN_SCHEMA if planning else None)
            if not isinstance(response.content,str) or not response.content.strip() or len(response.content)>16000: raise ProviderError("Provider returned invalid assistant text")
            mid=self._message(cid,"assistant","model",response.content,response)
            result={"message_id":mid,"model":response.model,"elapsed_seconds":response.elapsed_seconds,"plan":None}
            if planning:
                try: result["plan"]=PlanService(self.database).propose(cid,mid,parse_plan(response.content))
                except ValidationError as exc:
                    self._message(cid,"system","error",str(exc)+". No project was created. Revise your request and try Plan again.")
                    result["plan_error"]=str(exc)
            return result
        except ProviderError as exc:
            uncertain=exc.uncertain
            self._message(cid,"system","error",str(exc))
            return {"error":str(exc),"kind":"system","model_response":False}
        finally:
            with self.database.connect(write=True) as c:
                if uncertain: c.execute("UPDATE inference_claim SET uncertain=1 WHERE token=?",(token,))
                else: c.execute("DELETE FROM inference_claim WHERE token=?",(token,))

    def status(self):
        with self.database.connect() as c:
            row=c.execute("SELECT * FROM inference_claim").fetchone()
        return {**self.provider.availability(),"inference_claim":dict(row) if row else None}

    def reset_claim(self,reason):
        # Operator must first stop/restart Ollama; a dead client is not proof of server cancellation.
        required(reason,"reason")
        from .recovery import process_state
        with self.database.connect(write=True) as c:
            row=c.execute("SELECT * FROM inference_claim").fetchone()
            if c.execute("SELECT 1 FROM executions WHERE worker_id='research-synthesize' AND status='running'").fetchone():
                raise ValidationError('Cannot reset inference during a running synthesis execution')
            if row and not row["uncertain"] and process_state(row["owner_pid"])!="stopped": raise ValidationError("Inference owner is active; cannot reset")
            c.execute("DELETE FROM inference_claim")
            latest=c.execute("SELECT id FROM conversations ORDER BY updated_at DESC LIMIT 1").fetchone()
            if latest: audit(c,latest["id"],"inference_claim_reset",details={"reason":reason})
        return {"reset":True,"operator_attestation":reason}
