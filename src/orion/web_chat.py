"""Loopback-only development UI. Presentation calls services, never SQL."""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
from .conversations import ConversationService
from .plans import PlanService
from .ollama import OllamaProvider
from .models import ValidationError


def make_server(database,config,port=8765,provider=None):
    chat=ConversationService(database,provider or OllamaProvider(config))
    plans=PlanService(database)
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,value,html=False):
            data=value.encode() if html else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type","text/html; charset=utf-8" if html else "application/json")
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'nonce-"+token+"'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(data)
        def allowed(self):
            return self.headers.get("Host")==f"127.0.0.1:{self.server.server_port}"
        def do_GET(self):
            if not self.allowed(): return self.reply(403,{"error":"Use the exact loopback address"})
            parsed=urlsplit(self.path); query=parse_qs(parsed.query)
            try:
                if parsed.path=="/":
                    return self.reply(200,Path(__file__).with_name("chat.html").read_text(encoding="utf-8").replace("__TOKEN__",token),True)
                if parsed.path=="/api/status": result=chat.status()
                elif parsed.path=="/api/conversations": result=chat.list()
                elif parsed.path=="/api/projects": result=chat.projects()
                elif parsed.path=="/api/conversation":
                    cid=query.get("id",[""])[0]
                    result={"conversation":chat.get(cid),"messages":chat.messages(cid),"context":chat.context(cid),"plans":plans.list(cid)}
                else: return self.reply(404,{"error":"Not found"})
                self.reply(200,result)
            except (ValueError,RuntimeError) as exc: self.reply(400,{"error":str(exc)})
        def do_POST(self):
            origin=f"http://127.0.0.1:{self.server.server_port}"
            if not self.allowed() or self.headers.get("Origin")!=origin or self.headers.get("X-Orion-Token")!=token:
                return self.reply(403,{"error":"Local origin and request token required"})
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=20000: raise ValidationError("Invalid request size")
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValidationError("JSON object required")
                if self.path=="/api/conversations": result=chat.create(body.get("title","New conversation"),body.get("project_id") or None)
                elif self.path=="/api/message": result=chat.send(body["id"],body["text"],body.get("planning") is True)
                elif self.path=="/api/decision": result=plans.decide(body["id"],body["decision"],body["fingerprint"],body["reason"])
                else: return self.reply(404,{"error":"Not found"})
                self.reply(200,result)
            except (ValueError,RuntimeError,KeyError,TypeError) as exc: self.reply(400,{"error":str(exc)})
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    server.daemon_threads=True
    return server


def serve(database,config,port=8765):
    if not 1024<=port<=65535: raise ValidationError("Port must be 1024..65535")
    with make_server(database,config,port) as server:
        print(f"Orion CEO chat: http://127.0.0.1:{server.server_port} — local development only",flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
