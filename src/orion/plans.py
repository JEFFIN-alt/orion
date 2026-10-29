"""Immutable proposals; explicit atomic application through existing record services."""
import json
from uuid import uuid4
from .models import ValidationError, NotFoundError, required
from .service import Service, identifier, timestamp
from .dependencies import DependencyService
from .plan_schema import validate_plan, fingerprint, parse_plan


def audit(c, conversation_id, event, plan_id=None, details=None):
    c.execute("INSERT INTO chat_events VALUES (?,?,?,?,?,?)",(str(uuid4()),conversation_id,plan_id,event,json.dumps(details or {}),timestamp()))


class PlanService:
    def __init__(self,database): self.database=database

    def propose(self,conversation_id,message_id,body):
        validate_plan(body)
        plan_id=str(uuid4())
        with self.database.connect(write=True) as c:
            message=c.execute("SELECT * FROM messages WHERE id=? AND conversation_id=?",(identifier(message_id),identifier(conversation_id))).fetchone()
            if message is None or message["kind"]!="model": raise ValidationError("Plan requires a recorded model response")
            if fingerprint(parse_plan(message["content"])) != fingerprint(body): raise ValidationError("Proposal differs from the recorded model message")
            c.execute("INSERT INTO plans VALUES (?,?,?,?,?,?,?,?,?,?,?)",(plan_id,conversation_id,message_id,json.dumps(body),fingerprint(body),"proposed",timestamp(),None,None,None,None))
            audit(c,conversation_id,"plan_proposed",plan_id)
        return self.get(plan_id)

    def get(self,plan_id):
        with self.database.connect() as c:
            row=c.execute("SELECT * FROM plans WHERE id=?",(identifier(plan_id),)).fetchone()
            if row is None: raise NotFoundError("Plan not found")
            return self.decode(row)

    @staticmethod
    def decode(row):
        result=dict(row); result["body"]=json.loads(result.pop("body_json"))
        result["task_ids"]=json.loads(result.pop("task_ids_json") or "{}")
        return result

    def list(self,conversation_id):
        with self.database.connect() as c:
            return [self.decode(r) for r in c.execute("SELECT * FROM plans WHERE conversation_id=? ORDER BY rowid DESC LIMIT 30",(identifier(conversation_id),))]

    def decide(self,plan_id,decision,expected_fingerprint,reason):
        if decision not in ("approved","rejected"): raise ValidationError("Choose approved or rejected")
        reason=required(reason,"decision reason")
        with self.database.connect(write=True) as c:
            row=c.execute("SELECT * FROM plans WHERE id=?",(identifier(plan_id),)).fetchone()
            if row is None or row["status"]!="proposed": raise ValidationError("Plan missing or already decided")
            body=validate_plan(json.loads(row["body_json"]))
            if fingerprint(body)!=row["fingerprint"] or expected_fingerprint!=row["fingerprint"]: raise ValidationError("Plan differs from reviewed content; request a fresh proposal")
            project_id=None; tasks={}
            if decision=="approved":
                service=Service(self.database)
                project=service.create_project(body["title"],body["description"],connection=c); project_id=project["id"]
                for task in body["tasks"]:
                    description=task["description"]+"\nAcceptance criteria: "+json.dumps(task["acceptance_criteria"])+"\nProposed dependencies (plan keys): "+json.dumps(task["dependencies"])
                    created=service.create_task(project_id,task["title"],description,task["priority"],require_approval=True,connection=c)
                    tasks[task["key"]]=created["id"]
                for task in body["tasks"]:
                    for prerequisite in task["dependencies"]:
                        DependencyService(self.database).add(tasks[task["key"]], tasks[prerequisite], connection=c)
            c.execute("UPDATE plans SET status=?,decided_at=?,reason=?,project_id=?,task_ids_json=? WHERE id=?",(decision,timestamp(),reason,project_id,json.dumps(tasks),row["id"]))
            audit(c,row["conversation_id"],"plan_"+decision,row["id"],{"project_id":project_id,"task_ids":tasks})
        return self.get(plan_id)
