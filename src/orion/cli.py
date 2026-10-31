import argparse
import json
import sqlite3
import sys

from . import __version__
from .config import Config
from .database import Database
from .logging_config import configure
from .models import ValidationError
from .service import Service
from .execution import ExecutionService
from .workers import REGISTRY
from .approvals import ApprovalService
from .recovery import RecoveryService
from .inputs import InputService, DEFAULT_LIMITS
from .verification import VerificationService
from .provider import AIConfig, create_provider
from .conversations import ConversationService
from .dependencies import DependencyService
from .research import ResearchService, DEFAULTS


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Orion local project and task management")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--database")
    root.add_argument("--log-dir")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("status")
    dependencies = commands.add_parser("dependencies").add_subparsers(dest="action",required=True)
    add = dependencies.add_parser("add")
    add.add_argument("id")
    add.add_argument("prerequisite")
    dependencies.add_parser("show").add_argument("id")
    dependencies.add_parser("graph").add_argument("project")
    queue = commands.add_parser("queue").add_subparsers(dest="action",required=True)
    listing = queue.add_parser("list")
    listing.add_argument("project")
    listing.add_argument("--state",choices=("ready","waiting","blocked","completed"))
    queue.add_parser("explain").add_argument("id")
    research = commands.add_parser('research').add_subparsers(dest='action',required=True)
    research.add_parser('show').add_argument('id')
    research.add_parser('packet').add_argument('id')
    configure_research = research.add_parser('configure')
    configure_research.add_argument('id')
    configure_research.add_argument('--question',required=True)
    configure_research.add_argument('--providers',nargs='+',choices=('crossref','github'),default=DEFAULTS['providers'])
    configure_research.add_argument('--include-readme',action=argparse.BooleanOptionalAction,default=True)
    for key in ('crossref_limit','github_limit','request_budget','max_response_bytes','request_timeout','execution_timeout'):
        configure_research.add_argument('--'+key.replace('_','-'),type=int,default=DEFAULTS[key])
    from .synthesis import DEFAULTS as SYNTHESIS_DEFAULTS
    synthesis = commands.add_parser('synthesis').add_subparsers(dest='action',required=True)
    for action in ('show','evidence','packet','summary'):
        synthesis.add_parser(action).add_argument('id')
    synthesis_config = synthesis.add_parser('configure')
    synthesis_config.add_argument('id')
    synthesis_preview=synthesis.add_parser('preview')
    synthesis_preview.add_argument('id',help='Verified research execution ID')
    synthesis_preview.add_argument('--passages',type=json.loads,default=argparse.SUPPRESS)
    for key,value in SYNTHESIS_DEFAULTS.items():
        synthesis_preview.add_argument('--'+key.replace('_','-'),type=int,default=value)
    synthesis_config.add_argument('--source-execution',required=True)
    synthesis_config.add_argument('--passages', type=json.loads, default=argparse.SUPPRESS, help='JSON list of source_id, field, start, end selections; no filesystem paths')
    for key,value in SYNTHESIS_DEFAULTS.items():
        synthesis_config.add_argument('--'+key.replace('_','-'),type=int,default=value)
    serve=commands.add_parser("chat")
    serve.add_argument("--port",type=int,default=8765)
    commands.add_parser("ai-status")
    reset=commands.add_parser("ai-reset")
    reset.add_argument("--confirm-service-restarted",action="store_true",required=True)
    reset.add_argument("--reason",required=True)
    commands.add_parser("workers")
    run = commands.add_parser("execute")
    run.add_argument("id")
    run.add_argument("worker")
    commands.add_parser("execution").add_argument("id")
    commands.add_parser("history").add_argument("id")
    commands.add_parser("events").add_argument("--limit", type=int, default=50)
    approvals = commands.add_parser("approvals").add_subparsers(dest="action", required=True)
    approvals.add_parser("pending")
    approvals.add_parser("require").add_argument("id")
    approvals.add_parser("get").add_argument("id")
    request = approvals.add_parser("request")
    request.add_argument("id")
    request.add_argument("worker")
    request.add_argument("--reason", required=True)
    decision = approvals.add_parser("decide")
    decision.add_argument("id")
    decision.add_argument("decision", choices=("approved", "rejected"))
    decision.add_argument("--reason", required=True)
    recovery = commands.add_parser("recovery").add_subparsers(dest="action", required=True)
    recovery.add_parser("running")
    recovery.add_parser("inspect").add_argument("id")
    confirm = recovery.add_parser("confirm")
    confirm.add_argument("id")
    confirm.add_argument("--reason", required=True)
    inputs = commands.add_parser("inputs").add_subparsers(dest="action", required=True)
    importer = inputs.add_parser("import")
    importer.add_argument("source")
    importer.add_argument("--max-bytes", type=int, default=DEFAULT_LIMITS["max_bytes"])
    inputs.add_parser("list")
    inputs.add_parser("get").add_argument("id")
    binding = commands.add_parser("csv-config")
    binding.add_argument("id")
    binding.add_argument("--input", required=True, dest="input_id")
    for key, value in DEFAULT_LIMITS.items():
        binding.add_argument("--" + key.replace("_", "-"), type=int, default=value)
    commands.add_parser("verifications").add_argument("id")
    commands.add_parser("verify").add_argument("id")
    for kind in ("projects", "tasks"):
        group = commands.add_parser(kind).add_subparsers(dest="action", required=True)
        create = group.add_parser("create")
        create.add_argument("name" if kind == "projects" else "title")
        create.add_argument("--description", default="")
        if kind == "tasks":
            create.add_argument("--project", required=True, dest="project_id")
            create.add_argument("--priority", type=int, default=0)
            create.add_argument("--require-approval", action="store_true")
        listing = group.add_parser("list")
        if kind == "tasks":
            listing.add_argument("--project", dest="project_id")
        group.add_parser("get").add_argument("id")
        update = group.add_parser("update")
        update.add_argument("id")
        update.add_argument("--name" if kind == "projects" else "--title")
        update.add_argument("--description")
        if kind == "tasks":
            update.add_argument("--priority", type=int)
            update.add_argument("--summary")
        transition = group.add_parser("transition")
        transition.add_argument("id")
        transition.add_argument("status")
        if kind == "tasks":
            transition.add_argument("--summary")
    return root


def main(argv: list[str] | None = None) -> int:
    args = vars(parser().parse_args(argv))
    logger = None
    try:
        config = Config.load(args.pop("database"), args.pop("log_dir"))
        logger = configure(config.log_dir)
        db = Database(config.database)
        command = args.pop("command")
        if command == "init":
            db.initialize()
            result = {"database": str(config.database), "initialized": True}
        else:
            if not config.database.is_file():
                raise ValidationError("Database does not exist; run init first")
            health = db.health()
            if health["schema_version"] != 8 or health["integrity"] != "ok" or health["foreign_key_errors"]:
                raise ValidationError(f"Database is not healthy: {health}")
            if command in ("dependencies","queue"):
                dependencies = DependencyService(db)
                if args["action"] == "add": result = dependencies.add(args["id"],args["prerequisite"])
                elif args["action"] in ("show","explain"): result = dependencies.explain(args["id"])
                else:
                    result = dependencies.project(args["project"])
                    if args.get("state"): result["tasks"] = [t for t in result["tasks"] if t["classification"]==args["state"]]
            elif command == 'research':
                research = ResearchService(db)
                action = args.pop('action')
                task_id = args.pop('id')
                result = research.configure(task_id,**args) if action=='configure' else research.get(task_id) if action=='show' else research.packet(task_id)
            elif command == 'synthesis':
                from .synthesis import SynthesisService
                synthesis = SynthesisService(db)
                action = args.pop('action'); record_id = args.pop('id')
                result = synthesis.preview(record_id,**args) if action=='preview' else synthesis.configure(record_id,**args) if action=='configure' else synthesis.packet(record_id) if action=='packet' else synthesis.summary(record_id) if action=='summary' else synthesis.get(record_id)
            elif command == "chat":
                from .web_chat import serve
                serve(db,AIConfig.load(),args["port"])
                return 0
            elif command in ("ai-status","ai-reset"):
                chat=ConversationService(db,create_provider())
                result=chat.status() if command=="ai-status" else chat.reset_claim(args["reason"])
            elif command == "inputs":
                inputs = InputService(db)
                if args["action"] == "import":
                    result = inputs.import_csv(args["source"], args["max_bytes"])
                elif args["action"] == "get":
                    result = inputs.get(args["id"])
                else:
                    result = inputs.list()
            elif command == "csv-config":
                result = InputService(db).bind(args.pop("id"), args.pop("input_id"), **args)
            elif command in ("verify", "verifications"):
                verifier = VerificationService(db)
                result = verifier.verify(args["id"]) if command == "verify" else verifier.history(args["id"])
            elif command == "approvals":
                approvals = ApprovalService(db)
                action = args["action"]
                if action == "pending":
                    result = approvals.pending()
                elif action == "require":
                    result = approvals.require(args["id"])
                elif action == "get":
                    result = approvals.get(args["id"])
                elif action == "request":
                    result = approvals.request(args["id"], args["worker"], args["reason"])
                else:
                    result = approvals.decide(args["id"], args["decision"], args["reason"])
            elif command == "recovery":
                recovery = RecoveryService(db)
                if args["action"] == "running":
                    result = recovery.running()
                elif args["action"] == "inspect":
                    result = recovery.inspect(args["id"])
                else:
                    result = recovery.confirm(args["id"], args["reason"])
            elif command == "workers":
                result = [worker.describe() for worker in REGISTRY.values()]
            elif command in ("execute", "execution", "history", "events"):
                engine = ExecutionService(db)
                if command == "execute":
                    result = engine.execute(args["id"], args["worker"])
                elif command == "execution":
                    result = engine.get(args["id"])
                elif command == "history":
                    result = engine.history(args["id"])
                else:
                    result = engine.events(args["limit"])
            elif command == "status":
                result = {"version": __version__, "database": str(config.database), **health}
            else:
                service = Service(db)
                action = args.pop("action")
                record_id = args.pop("id", None)
                if action == "create":
                    result = (service.create_project if command == "projects" else service.create_task)(**args)
                elif action == "list":
                    result = service.list(command, **args)
                elif action == "get":
                    result = service.get(command, record_id)
                elif action == "update":
                    result = service.update(command, record_id, **{k: v for k, v in args.items() if v is not None})
                else:
                    result = service.transition(command, record_id, **args)
        logger.info("Command succeeded: %s", command)
        print(json.dumps(result, indent=2))
        return 1 if command in ("execute", "verify") and result["status"] == "failed" else 0
    except (ValidationError, sqlite3.Error, OSError, RuntimeError) as exc:
        if logger:
            logger.error("Command failed: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1
