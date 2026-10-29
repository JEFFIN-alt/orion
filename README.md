# Orion core foundation

Python 3.12, SQLite and the standard library. A deterministic report worker is included. No AI model, API or dashboard is included. This milestone manages durable records; completed means a manually recorded execution state, not proof that tests passed, requirements were verified, or a deliverable was approved. Persistent human approval is available; independent evaluation remains future work.

## Setup and use (PowerShell)

From `C:\Users\JEFFIN\Projects\orion`:

```powershell
.\.venv\Scripts\python.exe setup_dev.py
.\.venv\Scripts\python.exe -m orion init
.\.venv\Scripts\python.exe -m orion status
.\.venv\Scripts\python.exe -m orion projects create "CSV analysis" --description "First workflow"
.\.venv\Scripts\python.exe -m orion projects list
.\.venv\Scripts\python.exe -m orion tasks create "Validate input" --project <PROJECT_UUID> --priority 10
.\.venv\Scripts\python.exe -m orion tasks transition <TASK_UUID> in_progress
.\.venv\Scripts\python.exe -m orion tasks transition <TASK_UUID> completed --summary "Execution finished"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Replace UUID placeholders with returned identifiers. `setup_dev.py` registers src in this venv with a .pth file without installing dependencies. Rerun if the project moves. Packaging metadata is provided for later standard installation; building a distribution requires setuptools, which has not been installed by this milestone.

`projects` and `tasks` both support create, list, get, update and transition. Use command-level `--help`. Tasks list accepts `--project`. Updates accept name/title, description, and for tasks priority and summary. Priority is an integer 0â€“100; larger values sort first in project-filtered lists. An empty summary clears it to empty text. Identifiers are UUIDs. Output is JSON; errors go to stderr. Exit codes: 0 success, 1 application error, 2 CLI usage error.

## Configuration and storage

Global options `--database PATH --log-dir PATH` precede the command. Alternatively set ORION_DATABASE, ORION_LOG_DIR, ORION_HOME. Relative locations resolve against ORION_HOME, defaulting to this checkout root, not the caller's current directory. Defaults are data/orion.sqlite3 and logs/orion.log. Explicit locations are trusted operator configuration, not a security sandbox. Logs rotate at 1 MB with two backups. Runtime data, logs, secrets and the venv are ignored by Git.

Run init explicitly. Schema version 3 uses PRAGMA user_version. Repeated initialization preserves data; unsupported versions fail. Every connection enables foreign keys. Writes use BEGIN IMMEDIATE transactions with a five-second lock timeout, rollback on failure, and explicit connection closure. State checking and transitions occur under the same write transaction. SQL identifiers come only from internal allowlists; input values are parameterized. Timestamps are UTC. No delete operation is exposed.

Use status for SQLite integrity and foreign-key diagnostics. For a simple backup, stop all Orion commands, then copy the database file to a separate backup location. Restore only while Orion is stopped and validate the copy with status. Initialization migrates versions 1 and 2 to 3 transactionally. Automated backups are not implemented. Interrupted transactions roll back; previously persisted in_progress tasks remain visible for an explicit decision. There is no automatic task replay.

## State rules

Projects start active (available for work). Active can become paused, completed or cancelled. Paused means temporarily on hold and can become active or cancelled. Completed and cancelled are terminal administrative states. Project status does not automatically alter tasks or prevent record creation; completion does not certify child tasks.

Tasks start pending. Allowed transitions:

- pending: in_progress, cancelled
- in_progress: blocked, completed, failed, pending, cancelled
- blocked: in_progress, pending, cancelled
- failed: pending, cancelled
- completed and cancelled: terminal

Self-transitions and all other transitions fail without modifying the record. Returning in_progress to pending is an explicit requeue after interruption; the operator must check whether repeating prior work is safe. Summary is optional error/outcome text, not independent verification. A transition updates the modification timestamp atomically. There is no scheduling, dependency graph or generated-code sandbox. Worker executions have persistent history and events.

The small service module owns validation and transactional SQL together to avoid repository wrappers that only forward calls. Database configuration and lifecycle, state definitions, logging and CLI remain separate. Tests use temporary databases and logs, including fresh-process CLI verification; they never use real application data.


## Milestone 3: deterministic execution

Run `init` to migrate the existing database to schema 3. The migration adds executions and append-only events, preserving projects and tasks. Older schema versions must be explicitly migrated before other CLI operations.

```powershell
.\.venv\Scripts\python.exe -m orion workers
.\.venv\Scripts\python.exe -m orion execute <TASK_UUID> project-status
.\.venv\Scripts\python.exe -m orion execution <EXECUTION_UUID>
.\.venv\Scripts\python.exe -m orion history <TASK_UUID>
.\.venv\Scripts\python.exe -m orion events --limit 20
```

Only pending tasks execute. One running execution per database is enforced both by a write-transaction claim and a unique partial index. Manual task transitions cannot override a running execution. Separate databases are separate instances, not a machine-wide concurrency limit. There is no polling loop or automatic retry. To retry a failed task explicitly transition it to pending; attempt numbers increase and old attempts remain.

The registry describes trusted worker handlers, inputs, outputs, capabilities and completion conditions. Task input cannot specify Python code, imports, shell commands, URLs or output paths. The project-status worker receives only a consistent snapshot and returns JSON. It has no supplied database, network, shell or filesystem tools. These are code-level capabilities, not OS-enforced sandbox permissions: trusted Python code runs with the user's process privileges. The venv is not a sandbox.

The engine runs the handler in a spawned child process with a 10-second timeout, terminates it on timeout, validates the result against the captured source records, and writes an exclusively created UUID-named artifact under the database's parent directory/artifacts. ORION_DATABASE or --database therefore also selects the application data directory. Redirected artifact directories are rejected. Reports are limited to 10000 tasks and an 8 MB serialized input snapshot. Output validation and filesystem operations occur in the parent and do not have a separate hard wall-clock timeout. These limits support the sole trusted deterministic worker; do not register untrusted handlers.

A report describes its snapshot time. Its own task appears in_progress because completion happens only after artifact validation and persistence. It includes actual record text, which should be treated as local project data. Do not put secrets in task descriptions. The report is structurally/content validated by the engine, not independently evaluated.

Execution states: running means a durable claim exists; succeeded means handler output passed validation and the artifact was saved and read back; failed means an exception, timeout or validation/artifact error was recorded. Failures retain exception type, message and traceback in execution.error. Events store only identifiers and small operational details, not input snapshots. They record requested/started/succeeded/failed executions and manual task blocking. Rejected requests return errors before creating execution records. Cancellation is deferred.

## Milestone 4: approvals and conservative recovery

Schema 3 adds approval_policy, approvals, execution_ownership and recoveries; no existing table is dropped or rebuilt. The previous fifteen tests remain (the migration assertion now expects schema 3).

### Approval policy

Create a task with `tasks create TITLE --project ID --require-approval`, or use `approvals require TASK_ID` to permanently enable the gate for an existing task. `approvals request TASK_ID project-status --reason TEXT` also enables the gate. There is deliberately no policy-disable command. Unprotected existing tasks preserve their previous behavior.

Use `approvals pending`, `approvals get APPROVAL_ID`, and `approvals decide APPROVAL_ID approved|rejected --reason TEXT`. Only pending requests can receive a decision. Decisions cannot be changed; approval does not execute a task. Review proposal_json before deciding: it contains the exact proposed source records and parameters, while routine events carry only identifiers and hashes.

The SHA-256 fingerprint binds the task ID, worker ID and declared version/definition, timeout, resolved data directory, project and all project task records (including timestamps). This is deliberately conservative: any source record change requires a fresh approval, even edits later reverted. The engine checks and consumes a matching unused approval within the same BEGIN IMMEDIATE transaction that claims execution and captures the source snapshot. The report uses that snapshot, with only the executing task's operational state/timestamp changed to in_progress. Concurrent edits cannot replace the approved input after the check. Worker implementation changes MUST bump Worker.version. The registry and application source are trusted, not a security boundary against code modification.

Approvals authorize one attempt. Failure and explicit requeue require a new request and decision. Missing, pending, rejected, consumed, differently configured and stale approvals cannot authorize execution, including direct ExecutionService calls. Denials and stale approvals generate durable audit events without rewriting the original decision. Staleness is checked at execution time; the old request remains historically approved but no longer authorizes the changed operation. Fingerprints and source snapshots may contain private project data; keep secrets out of task fields.

### Recovery commands and evidence

- `recovery running`: inspect all running records, ownership, safety reasons and artifact presence.
- `recovery inspect EXECUTION_ID`: dry-run inspection. It does not change task/execution state; it appends an inspection event.
- `recovery confirm EXECUTION_ID --reason TEXT`: recheck under a write transaction and confirm interruption only if safe. Reasons must be nonempty.
- `execution EXECUTION_ID`, `history TASK_ID`, `events --limit 50`: inspect original attempts and decisions.

Ownership records contain local host, parent PID, child PID, launch phase and recording timestamp. The engine persists not_started before launch, starting before process.start, running with the child PID after launch, and stopped only after confirmed child exit. A crash in the starting window is ambiguous even if the parent is gone. Legacy executions without ownership are also unresolved.

Recovery requires the parent to be proven stopped and the child to be proven stopped or never launched. Windows process handles are queried read-only using the standard library's ctypes; inaccessible or unknown process evidence refuses recovery. A reused PID that is active conservatively blocks recovery. No timeout, timestamp or missing heartbeat proves death. Evidence applies to this local machine: do not copy running databases between machines or reuse a host name to make ownership appear local.

The confirmation transaction serializes competing recovery and execution requests. It preserves the attempt ID/start/result, records the operator reason and evidence in recoveries, marks the execution failed with an explicit interrupted/unknown-outcome explanation, and blocks the task for review. It never infers success from an artifact, deletes an artifact, requeues or starts work. Use history to inspect consumed approvals, and inspect partial outputs before explicitly transitioning blocked to pending. Approval-required tasks then need a fresh request.

Ordinary worker exceptions/timeouts still produce failed attempts. If child termination cannot be established, the claim remains running. A hard parent crash may leave a real child alive: orphan prevention is not guaranteed, and recovery must wait for that child to exit. Recovery does not terminate processes. Unknown ownership, access denial or an ambiguous launch remains unresolved and requires administrative investigation; there is intentionally no force-clear flag. A terminal successful record cannot be recovered or rewritten.

### Remaining limits and operational procedure

Back up the stopped application's database and retain artifacts before administrative repair. Inspect a candidate, verify that the recorded processes are no longer active, and use confirm only with an accurate reason; the command still performs its own checks. Inspect history/events afterward. For unresolved cases, investigate OS process information rather than editing away the running flag. No automatic retries, cancellation, approvals authentication/multiple-user roles, remote process tracking, or OS security sandbox is implemented. A local user with direct database/code write access can bypass application policy. Only the trusted deterministic report worker is supported; worker capabilities do not permit spawning descendants, and recovery does not track arbitrary process trees.

The handler has a timeout; parent-side validation/filesystem operations are not separately hard-timed. The database and artifact file are not one atomic transaction: an orphan or partial file is retained for review and never promoted to success by recovery. Automated power-loss/corruption recovery is not claimed.

Tests use temporary databases, retain all original behavior checks, and add approval binding/single use, durable decisions and denial events, schema-2 migration, active and unknown process refusal, concurrent recovery, preserved artifacts, and a real controlled parent crash with an independently surviving child. These are deterministic software workflows, not AI reasoning or independent evaluation.
