"""Loopback-only development UI. Presentation calls services, never SQL."""
import json
import secrets
import os
import sqlite3
import threading
import time
import hashlib
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
from .conversations import ConversationService
from .plans import PlanService
from .provider import create_provider
from .models import ValidationError, NotFoundError
from .control_room import ControlRoom
from .approvals import ApprovalService
from .task_lifecycle import TaskLifecycle
from .task_workers import TaskWorkers
from .inputs import InputService

logger=logging.getLogger('orion.web')


def make_server(database,config,port=8765,provider=None):
    chat=ConversationService(database,provider or create_provider(config))
    plans=PlanService(database)
    room=ControlRoom(database,config)
    lifecycle=TaskLifecycle(database)
    token=secrets.token_urlsafe(32)
    confirmations={}
    previews={}
    requests={}
    request_lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,value,html=False,content_type=None):
            def redact(value):
                key=os.getenv('ORION_GROQ_API_KEY','')
                if isinstance(value,str): return value.replace(key,'[redacted]') if key else value
                if isinstance(value,dict): return {k:redact(v) for k,v in value.items()}
                if isinstance(value,list): return [redact(v) for v in value]
                return value
            data=value.encode() if html else json.dumps(redact(value)).encode()
            self.send_response(status)
            self.send_header("Content-Type",content_type or ("text/html; charset=utf-8" if html else "application/json"))
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'nonce-"+token+"'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try: self.wfile.write(data)
            except OSError: pass
        def allowed(self):
            return self.headers.get("Host")==f"127.0.0.1:{self.server.server_port}"
        def do_GET(self):
            if not self.allowed(): return self.reply(403,{"error":"Use the exact loopback address"})
            parsed=urlsplit(self.path); query=parse_qs(parsed.query)
            try:
                if parsed.path=="/":
                    return self.reply(200,Path(__file__).with_name("chat.html").read_text(encoding="utf-8").replace("__TOKEN__",token),True)
                if parsed.path in ('/control-room.js','/control-room.css'):
                    name=parsed.path[1:]
                    return self.reply(200,Path(__file__).with_name(name).read_text(encoding='utf-8'),True,
                                      'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8')
                record_id=query.get('id',[''])[0]
                if parsed.path=="/api/status":
                    result=chat.status()
                    result['loaded']=None
                    if config.provider=='ollama' and result.get('service_available'):
                        try:
                            from .ollama import OllamaProvider
                            result['loaded']=any(m.get('name',m.get('model'))==config.model for m in OllamaProvider(config)._request('/api/ps',timeout=3).get('models',[]))
                        except (ValueError,RuntimeError,OSError): pass
                elif parsed.path=='/api/overview': result=room.overview()
                elif parsed.path=='/api/workers': result=room.workers()
                elif parsed.path=='/api/worker-catalog': result=lifecycle.catalog()
                elif parsed.path=='/api/inputs': result=InputService(database).list()
                elif parsed.path=='/api/artifact': result=lifecycle.artifact(record_id)
                elif parsed.path=='/api/task-preview':
                    result=lifecycle.preview(record_id)
                    nonce=secrets.token_urlsafe(32)
                    with request_lock:
                        for key in list(previews):
                            if previews[key]['expires']<time.monotonic(): del previews[key]
                        if len(previews)>=100: raise ValidationError('Too many previews; inspect again later')
                        previews[nonce]={'id':record_id,'fingerprint':result['fingerprint'],'expires':time.monotonic()+180}
                    result['preview_token']=nonce
                elif parsed.path=='/api/tasks': result=room.tasks(query.get('project',[None])[0])
                elif parsed.path=='/api/task': result=room.task(record_id)
                elif parsed.path=='/api/executions': result=room.executions()
                elif parsed.path=='/api/execution': result=room.execution(record_id)
                elif parsed.path=='/api/approvals': result=room.approvals()
                elif parsed.path=='/api/approval': result=room.approval(record_id)
                elif parsed.path=='/api/research': result=room.research()
                elif parsed.path=='/api/evidence': result=room.evidence(record_id)
                elif parsed.path=="/api/conversations": result=chat.list()
                elif parsed.path=="/api/projects": result=room.projects()
                elif parsed.path=="/api/conversation":
                    cid=query.get("id",[""])[0]
                    result={"conversation":chat.get(cid),"messages":chat.messages(cid),"context":chat.context(cid),"plans":plans.list(cid)}
                else: return self.reply(404,{"error":"Not found"})
                self.reply(200,result)
            except NotFoundError as exc: self.reply(404,{'error':str(exc)})
            except (ValueError,RuntimeError) as exc: self.reply(400,{"error":str(exc)})
            except sqlite3.OperationalError:
                logger.exception('Unexpected database operation error during web GET')
                self.reply(500,{'error':'Internal error; see the Orion log'})
            except (OSError,sqlite3.Error): self.reply(503,{'error':'Local data unavailable. Inspect the database and artifacts.'})
            except Exception:
                logger.exception('Unexpected web GET error')
                self.reply(500,{'error':'Internal error; see the Orion log'})
        def do_POST(self):
            origin=f"http://127.0.0.1:{self.server.server_port}"
            if not self.allowed() or self.headers.get("Origin")!=origin or self.headers.get("X-Orion-Token")!=token:
                return self.reply(403,{"error":"Local origin and request token required"})
            request_id=self.headers.get('X-Orion-Request')
            claimed=False
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=20000: raise ValidationError("Invalid request size")
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValidationError("JSON object required")
                if request_id:
                    if len(request_id)>100: raise ValidationError('Invalid request identifier')
                    signature=hashlib.sha256((self.path+json.dumps(body,sort_keys=True)).encode()).hexdigest()
                    with request_lock:
                        for key in list(requests):
                            if requests[key]['expires']<time.monotonic(): del requests[key]
                        previous=requests.get(request_id)
                        if previous:
                            if previous['signature']!=signature or 'result' not in previous:
                                return self.reply(409,{'error':'Request already in progress or identifier reused'})
                            return self.reply(200,previous['result'])
                        if len(requests)>=256: raise ValidationError('Request queue full; try later')
                        requests[request_id]={'signature':signature,'expires':time.monotonic()+600}
                        claimed=True
                if self.path=="/api/conversations": result=chat.create(body.get("title","New conversation"),body.get("project_id") or None)
                elif self.path=="/api/message": result=chat.send(body["id"],body["text"],body.get("planning") is True)
                elif self.path=="/api/decision": result=plans.decide(body["id"],body["decision"],body["fingerprint"],body["reason"])
                elif self.path=='/api/projects':
                    if set(body)-{'name','description'}: raise ValidationError('Unsupported project field')
                    if any(not isinstance(v,str) or len(v)>4000 for v in body.values()): raise ValidationError('Invalid project text')
                    result=room.service.create_project(body['name'],body.get('description',''))
                elif self.path=='/api/tasks':
                    if set(body)-{'title','description','project_id','priority'}: raise ValidationError('Unsupported task field')
                    if any(not isinstance(body.get(k,''),str) or len(body.get(k,''))>4000 for k in ('title','description','project_id')): raise ValidationError('Invalid task text')
                    result=room.service.create_task(body['project_id'],body['title'],body.get('description',''),body.get('priority',0),require_approval=True)
                elif self.path=='/api/task-assignment':
                    if set(body)!={'id','worker_id'}: raise ValidationError('Task and registered worker IDs required')
                    result=TaskWorkers(database).assign(body['id'],body['worker_id'])
                elif self.path=='/api/task-configuration':
                    if set(body)!={'id','assignment_id','configuration'}: raise ValidationError('Task, assignment and configuration required')
                    result=lifecycle.configure(body['id'],body['assignment_id'],body['configuration'])
                elif self.path=='/api/task-approval':
                    if set(body)!={'preview_token','reason'}: raise ValidationError('Inspected preview and reason required')
                    reason=body['reason']
                    if not isinstance(reason,str) or not 1<=len(reason.strip())<=2000: raise ValidationError('Decision reason required')
                    with request_lock: preview=previews.pop(body['preview_token'],None)
                    if preview is None or preview['expires']<time.monotonic(): raise ValidationError('Preview expired or used; inspect again')
                    result=lifecycle.request(preview['id'],reason,preview['fingerprint'])
                    result.pop('proposal_json',None)
                elif self.path=='/api/task-execute':
                    if set(body)!={'id'} or not request_id: raise ValidationError('Task ID and unique request identifier required')
                    result=lifecycle.execute(body['id'])
                elif self.path=='/api/approval-confirmation':
                    decision=body['decision']; reason=body['reason']
                    if decision not in ('approved','rejected') or not isinstance(reason,str) or not 1<=len(reason.strip())<=2000: raise ValidationError('Valid decision and reason required')
                    approval=room.approval(body['id'])
                    if not approval['can_decide']: raise ValidationError('Proposal is stale, consumed or already decided')
                    nonce=secrets.token_urlsafe(32)
                    with request_lock:
                        for key in list(confirmations):
                            if confirmations[key]['expires']<time.monotonic(): del confirmations[key]
                        if len(confirmations)>=100: raise ValidationError('Too many confirmations; wait and inspect again')
                        confirmations[nonce]={'id':approval['id'],'decision':decision,'reason':reason,
                                              'fingerprint':approval['fingerprint'],'expires':time.monotonic()+180}
                    result={'confirmation':nonce,'approval':approval,'decision':decision,'reason':reason,'expires_seconds':180}
                elif self.path=='/api/approval-decision':
                    with request_lock: confirmation=confirmations.pop(body['confirmation'],None)
                    if confirmation is None or confirmation['expires']<time.monotonic(): raise ValidationError('Confirmation expired or used; inspect again')
                    result=ApprovalService(database).decide(confirmation['id'],confirmation['decision'],confirmation['reason'],expected_fingerprint=confirmation['fingerprint'])
                    result.pop('proposal_json',None)
                else: return self.reply(404,{"error":"Not found"})
                if claimed:
                    with request_lock: requests[request_id]['result']=result
                self.reply(200,result)
            except NotFoundError as exc: self.reply(404,{'error':str(exc)})
            except (ValueError,RuntimeError,KeyError,TypeError) as exc: self.reply(400,{"error":str(exc)})
            except sqlite3.OperationalError:
                logger.exception('Unexpected database operation error during web POST')
                self.reply(500,{'error':'Internal error; see the Orion log'})
            except (OSError,sqlite3.Error): self.reply(503,{'error':'Local data unavailable. Inspect the database and artifacts.'})
            except Exception:
                logger.exception('Unexpected web POST error')
                self.reply(500,{'error':'Internal error; see the Orion log'})
            finally:
                if claimed:
                    with request_lock:
                        if request_id in requests and 'result' not in requests[request_id]: del requests[request_id]
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    server.daemon_threads=True
    return server


def serve(database,config,port=8765):
    if not 1024<=port<=65535: raise ValidationError("Port must be 1024..65535")
    with make_server(database,config,port) as server:
        print(f"Orion CEO chat: http://127.0.0.1:{server.server_port} — local development only",flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
