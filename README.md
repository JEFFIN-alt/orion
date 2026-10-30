# Orion core foundation

Python 3.12, SQLite and the standard library. Orion includes persistent projects, approved plans, deterministic workers, a local CEO chat interface and dependency-aware workflow inspection. No model is bundled. A task marked completed is not by itself evidence of successful work: dependency eligibility requires execution evidence and any required verification. General independent evaluation remains future work.

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

Run init explicitly. Schema version 8 uses PRAGMA user_version. Repeated initialization preserves data; unsupported versions fail. Every connection enables foreign keys. Writes use BEGIN IMMEDIATE transactions with a five-second lock timeout, rollback on failure, and explicit connection closure. State checking and transitions occur under the same write transaction. SQL identifiers come only from internal allowlists; input values are parameterized. Timestamps are UTC. No delete operation is exposed.

Use status for SQLite integrity and foreign-key diagnostics. For a simple backup, stop all Orion commands, then copy the database file to a separate backup location. Restore only while Orion is stopped and validate the copy with status. Initialization migrates versions 1 through 7 to 8 transactionally. Automated backups are not implemented. Interrupted transactions roll back; previously persisted in_progress tasks remain visible for an explicit decision. There is no automatic task replay.

## State rules

Projects start active (available for work). Active can become paused, completed or cancelled. Paused means temporarily on hold and can become active or cancelled. Completed and cancelled are terminal administrative states. Project status does not automatically alter tasks or prevent record creation; completion does not certify child tasks.

Tasks start pending. Allowed transitions:

- pending: in_progress, cancelled
- in_progress: blocked, completed, failed, pending, cancelled
- blocked: in_progress, pending, cancelled
- failed: pending, cancelled
- completed and cancelled: terminal

Self-transitions and all other transitions fail without modifying the record. Returning in_progress to pending is an explicit requeue after interruption; the operator must check whether repeating prior work is safe. Summary is optional error/outcome text, not independent verification. A transition updates the modification timestamp atomically. Dependency readiness is derived separately from task state; there is no automatic scheduler or generated-code sandbox. Worker executions have persistent history and events.

The small service module owns validation and transactional SQL together to avoid repository wrappers that only forward calls. Database configuration and lifecycle, state definitions, logging and CLI remain separate. Tests use temporary databases and logs, including fresh-process CLI verification; they never use real application data.


## Milestone 3: deterministic execution

Run `init` to migrate the existing database to schema 8. The migration adds executions and append-only events, preserving projects and tasks. Older schema versions must be explicitly migrated before other CLI operations.

```powershell
.\.venv\Scripts\python.exe -m orion workers
.\.venv\Scripts\python.exe -m orion execute <TASK_UUID> project-status
.\.venv\Scripts\python.exe -m orion execution <EXECUTION_UUID>
.\.venv\Scripts\python.exe -m orion history <TASK_UUID>
.\.venv\Scripts\python.exe -m orion events --limit 20
```

Only pending tasks execute. One running execution per database is enforced both by a write-transaction claim and a unique partial index. Manual task transitions cannot override a running execution. Separate databases are separate instances, not a machine-wide concurrency limit. There is no polling loop or automatic retry. To retry a failed task explicitly transition it to pending; attempt numbers increase and old attempts remain.

The registry describes trusted worker handlers, inputs, outputs, capabilities and completion conditions. Task input cannot specify Python code, imports, shell commands, URLs or output paths. The project-status worker receives only a consistent snapshot and returns JSON. It has no supplied database, network, shell or filesystem tools. These are code-level capabilities, not OS-enforced sandbox permissions: trusted Python code runs with the user's process privileges. The venv is not a sandbox.

The engine runs the handler in a spawned child process with a 10-second timeout, terminates it on timeout, validates the result against the captured source records, and writes an exclusively created UUID-named artifact under the database's parent directory/artifacts. ORION_DATABASE or --database therefore also selects the application data directory. Redirected artifact directories are rejected. Reports are limited to 10000 tasks and an 8 MB serialized input snapshot. Output validation and filesystem operations occur in the parent and do not have a separate hard wall-clock timeout. These limits support the project-status worker; do not register untrusted handlers.

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

Back up the stopped application's database and retain artifacts before administrative repair. Inspect a candidate, verify that the recorded processes are no longer active, and use confirm only with an accurate reason; the command still performs its own checks. Inspect history/events afterward. For unresolved cases, investigate OS process information rather than editing away the running flag. No automatic retries, cancellation, approvals authentication/multiple-user roles, remote process tracking, or OS security sandbox is implemented. A local user with direct database/code write access can bypass application policy. Only registered trusted deterministic workers are supported; worker capabilities do not permit spawning descendants, and recovery does not track arbitrary process trees.

The handler has a timeout; parent-side validation/filesystem operations are not separately hard-timed. The database and artifact file are not one atomic transaction: an orphan or partial file is retained for review and never promoted to success by recovery. Automated power-loss/corruption recovery is not claimed.

Tests use temporary databases, retain all original behavior checks, and add approval binding/single use, durable decisions and denial events, schema-2 migration, active and unknown process refusal, concurrent recovery, preserved artifacts, and a real controlled parent crash with an independently surviving child. These are deterministic software workflows, not AI reasoning. CSV-specific independent verification is described below.


## Milestone 5: controlled CSV analysis and verification

Schema 4 adds inputs, csv_operations, execution_inputs and immutable verifications. It preserves all project, task, execution, event, approval and recovery tables. Run init explicitly after backing up an existing database.

The import command is the only new operation that accepts a source path. It copies a bounded regular file into data/inputs/UUID.csv, records its basename (not absolute source path), byte size, SHA-256 digest and import time, and never overwrites a registered asset. Input paths, linked source paths, redirected managed directories and malformed identifiers are rejected. Managed input metadata is immutable through the API; changed bytes must be imported as a new asset. Import preserves bytes; UTF-8 and CSV structural validation happen during execution. An interrupted copy/database failure can leave an unregistered file, which the worker cannot resolve by ID.

The data directory is the configured database's parent. inputs/ and artifacts/ are separate managed subdirectories. Set --database or ORION_DATABASE to relocate both consistently. No worker accepts an output path or a source filesystem path. The engine supplies digest-checked bounded bytes to the child. These application controls are not an OS sandbox and do not defend against malicious local code racing filesystem operations or rewriting the database.

### Commands

```powershell
$python = '.\.venv\Scripts\python.exe'
$asset = & $python -m orion inputs import '.\sample.csv' | ConvertFrom-Json
& $python -m orion inputs list
& $python -m orion inputs get $asset.id
$project = & $python -m orion projects create 'CSV analysis' | ConvertFrom-Json
$task = & $python -m orion tasks create 'Profile CSV' --project $project.id --require-approval | ConvertFrom-Json
& $python -m orion csv-config $task.id --input $asset.id
$request = & $python -m orion approvals request $task.id csv-profile --reason 'Review imported input and limits' | ConvertFrom-Json
& $python -m orion approvals get $request.id
& $python -m orion approvals decide $request.id approved --reason 'Reviewed exact operation'
$run = & $python -m orion execute $task.id csv-profile | ConvertFrom-Json
& $python -m orion history $task.id
& $python -m orion verifications $run.id
Get-Content -LiteralPath $run.result.artifact
& $python -m orion verify $run.id
```

csv-config stores input ID and limits against a pending task; it cannot alter a running task. Bind before requesting approval. Rebinding, changing a limit, changing source records, worker version, task or input invalidates the approval. The fingerprint includes the imported byte digest, and the engine rereads/checks those bytes before claiming execution. The worker runs against that captured byte snapshot. Verification rereads the managed input after execution; changing it during the run causes verification to fail. Authorization remains single-use, and failed attempts do not automatically retry.

### CSV policy and resource limits

Defaults (also hard ceilings in this milestone): 10 MiB input bytes, 100000 data rows, 200 columns, 65536 characters per field including headers. Lower limits are configurable with csv-config --max-bytes, --max-rows, --max-columns and --max-field-size; imports also accept --max-bytes. Invalid/oversized values are rejected. Reads are capped at limit+1 bytes, field limits apply during CSV parsing, and row/column checks never silently truncate. Saved artifacts have a separate 4 MiB verification ceiling. The existing child timeout is 10 seconds; parent-side verification is bounded by input limits but has no independent hard timeout.

Inputs must be UTF-8, optionally with BOM. The dialect is comma-separated Excel-style CSV: double-quote quoting, doubled internal quotes, strict csv.reader parsing, no dialect sniffing or expression evaluation. Headers are trimmed, must be nonempty, and must be unique under case-sensitive comparison after trimming. Header-only datasets are valid with zero rows and empty columns. A missing header, malformed quoting, invalid encoding, empty header, duplicate header, inconsistent row width or exceeded limit fails execution. Blank data lines are not discarded; they fail width validation. Errors report a check/row number, not raw row contents.

Only blank or whitespace-only cells are missing. NA and null are text. Type inference examines every non-missing cell. A column is numeric only when all its non-missing cells match ordinary signed ASCII decimal/scientific notation and are finite Decimal values, with nonzero adjusted decimal exponents between -308 and 308. NaN, infinity, mixed text, underscores and values outside this range make the entire column text. All-missing columns are empty, not numeric.

Numeric output contains observation count, minimum, maximum and mean. Summation and division use a 50-significant-digit Decimal context. Numeric values are JSON strings to preserve explicit decimal representation and avoid binary-float overflow; counts remain JSON integers. This is rounded decimal arithmetic, not arbitrary-precision exact statistics. Reports are deterministic for the same bytes, version, limits and supplied analysis timestamp; real runs have distinct timestamps and execution IDs. No raw data rows or absolute filesystem paths appear in the report.

### Independent verification and failure evidence

The engine exclusively creates a temporary report, flushes it, then publishes the execution-named JSON using a hard link that fails if the destination exists. This provides atomic visibility without overwriting; it requires hard-link support (tested on this Windows filesystem). The temporary file is removed after publication. Unsupported filesystems fail explicitly. SQLite and the filesystem do not share an atomic transaction; partial/orphan files remain evidence and are not promoted by recovery.

verification.py never invokes csv_worker.profile or its output validator. It rereads the original managed input, reads bounded saved artifact bytes, checks recorded digests, parses JSON with duplicate/nonfinite-value rejection, validates schema/metadata, independently parses CSV, and recomputes dimensions, missing/non-missing counts, types and numeric summaries. It checks input/artifact digests again before recording its result. Both paths use Python's CSV/Decimal standard libraries, so this is independent implementation of checks, not independent third-party certification.

Verification rows record verifier/version, execution, observed digests, timestamp, individual checks and passed/failed outcome. Checks stop at the first failed prerequisite, retaining the checks actually performed. A missing or modified artifact produces a failed record. Invalid CSV that fails before producing an artifact has a failed execution and no verification row. Preflight missing/tampered assets are rejected before an execution is created.

CSV execution is marked succeeded only after a passed verification is persisted. Verification failure marks that attempt and task failed and preserves the artifact and verification record. If final persistence is interrupted, existing conservative recovery rules apply. The project-status worker remains content-validated without being relabeled independently verified.

verify EXECUTION_ID explicitly rechecks current files and appends a new immutable result (exit 1 on failed verification); verifications lists the history. execution/history include latest_verification for CSV runs. A later tamper check does not rewrite the historical successful attempt or initial verification: use latest_verification to assess current saved bytes. Verification proves the recorded digests at the time checked, not perpetual immutability. All verification/asset/analysis events avoid copying row contents into logs.

No charts, PDF export, data cleaning, missing-token inference, arbitrary encodings/dialects, generated code, AI models or web dashboard are included. The next useful extension is a readable report view and additional numerical/property tests before expanding analysis scope.

## Milestone 6: local CEO chat

Run `python -m orion init` to migrate to schema 8, then `python -m orion chat`. Open http://127.0.0.1:8765 (use this exact host). Use the existing .venv interpreter. This is a local development HTTP application, not a public production service. No new Python dependencies are required. Stop with Ctrl+C. The UI includes conversations, selected project context, provider availability, model-labelled responses, structured plans and explicit decisions. Choose Propose plan for natural-language planning; ordinary Send message is discussion only.

Schema 5 adds conversations, messages, immutable-content plans, append-only chat_events and a single inference claim. Existing tables are preserved. The UI calls application services; it contains no SQL. The service contract is Provider; OllamaProvider uses local HTTP /api/tags and /api/chat with no tools, proxies or redirects. Configuration: ORION_AI_PROVIDER=ollama, ORION_AI_ENDPOINT=http://127.0.0.1:11434, ORION_AI_MODEL=qwen3.5:2b-q4_K_M, ORION_AI_TIMEOUT=90, ORION_AI_CONTEXT=4096, ORION_AI_MAX_OUTPUT=1024. Endpoint validation permits only loopback. Model downloads are never automatic. `python -m orion ai-status` reports readiness.

Ollama is a prerequisite, not bundled with Orion. At implementation time no Ollama installation/model was found and the service refused connections. No real inference was performed. Download/install Ollama from https://ollama.com/download/windows, then open a new PowerShell and check `ollama --version`. Close memory-heavy applications before trying inference. The official model tag https://ollama.com/library/qwen3.5:2b-q4_K_M lists a 1.9 GB download; installation itself also needs storage. Model fit/quality is unverified on this laptop.

To run a single-request Ollama service, first quit any Ollama tray instance; then in a dedicated PowerShell:

```powershell
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='1'
ollama serve
```

In a second PowerShell:

```powershell
ollama pull qwen3.5:2b-q4_K_M
ollama list
Set-Location 'C:\Users\JEFFIN\Projects\orion'
$env:ORION_AI_MODEL='qwen3.5:2b-q4_K_M'
$env:ORION_AI_CONTEXT='4096'
.\.venv\Scripts\python.exe -m orion ai-status
.\.venv\Scripts\python.exe -m orion chat
```

Ollama's default model storage is outside this repository. Do not set OLLAMA_MODELS inside the checkout. The adapter requests no thinking output and unloads after each response (keep_alive=0) to reduce idle memory use. Request errors never turn into fabricated assistant replies. Messages carry user/model/system/error kind plus actual returned model/provider and elapsed request time. Model reasoning/quality cannot be guaranteed; a valid schema does not mean a good plan.

Conversation listings are capped at 100, message retrieval at the latest 100, inference history at 20 recent messages and a bounded UTF-8 byte budget. The model context is limited through num_ctx; text byte budgeting is an approximation, not exact tokenization. Context contains only selected project metadata and up to ten task summaries, with a smaller excerpt sent to the model. No environment variables, credentials, files or whole database are sent. Context may omit older details. User messages are limited to 2000 UTF-8 bytes. Outputs are capped and plans are strictly validated: exact fields, up to 8 tasks, integer priorities, acceptance criteria, valid dependency references, no cycles. Invalid output is retained and accompanied by a system error; refine the request and choose Propose plan again.

Plans are proposals until a human decision. Approval binds the displayed fingerprint, creates project/tasks through the existing service in one transaction, and records the decision. Repeated decisions fail. Plan content is immutable: revised proposals receive a new ID and fresh approval. Every generated task requires separate execution approval. Acceptance criteria and dependency references are retained in plan JSON and task descriptions. Newly approved plans also register enforced task dependencies atomically (see Milestone 7). The chatbot has no execution, shell, SQL, filesystem or browsing tools.

Only one inference claim per database is allowed. A timeout/uncertain connection outcome retains the claim because a disconnected client does not prove Ollama stopped computing. After stopping/restarting Ollama and ensuring the old Orion caller is gone, use `python -m orion ai-reset --confirm-service-restarted --reason "Restarted Ollama and checked prior request"`. An active non-uncertain owner cannot be reset. A hard crash may require this manual reset. This is not a machine-wide lock against other unrelated Ollama clients or other Orion databases; keep Ollama's parallelism at one and do not run competing clients.

The web server validates Host, Origin and a per-server request token; model text and plans are rendered as text rather than HTML. No public authentication or remote deployment is supported. Browser automation was disabled during verification, so HTTP routes, missing-model behavior and JavaScript syntax were checked; rendered visual behavior remains unverified. Fake-provider tests and local HTTP fixtures validate integration only, not real AI quality. A real greeting and planning integration test must be run once Ollama/model installation is complete.


## Milestone 7: dependency-aware workflows

Run `init` explicitly to migrate to schema 6. Back up existing data first. The migration adds `task_dependencies` and its constraints/index/triggers without rebuilding existing tables. Each edge records dependent task, prerequisite and creation time. Foreign keys, unique pairs, same-project checks and a recursive cycle check protect registration. Edges cannot be rewritten; no removal API is provided. Registration is restricted to pending dependent tasks. Old plans approved before this migration are not retrospectively converted from descriptions; review and explicitly register dependencies for their pending tasks.

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m orion dependencies add <DEPENDENT_ID> <PREREQUISITE_ID>
& $python -m orion dependencies show <TASK_ID>
& $python -m orion dependencies graph <PROJECT_ID>
& $python -m orion queue list <PROJECT_ID>
& $python -m orion queue list <PROJECT_ID> --state ready
& $python -m orion queue list <PROJECT_ID> --state waiting
& $python -m orion queue list <PROJECT_ID> --state blocked
& $python -m orion queue explain <TASK_ID>
```

Inspection uses a consistent read transaction and writes no task, execution or event records. Ordinary CLI diagnostic logging may still write to the log file. Output is JSON, sorted by descending priority, creation time and ID. Each task includes its persistent state, derived classification, exact prerequisite IDs, reasons and applicable execution/verification IDs. Inspection is bounded to 10000 project tasks and never starts workers.

A prerequisite is eligible only if its task is completed, its latest attempt (highest attempt number for that task) succeeded, and its own prerequisites are eligible. Unknown workers fail closed. Worker.required_verifier declares independent verification policy. For csv-profile the most recently inserted verification for the applicable execution must pass using csv-independent and match both input and artifact digests recorded for that execution. A missing verification or a later failed/mismatched verification blocks eligibility; an explicit later passing re-verification can restore it. project-status requires engine validation, not independent verification. Manual completion, old successful attempts superseded by failure, and another task's success do not qualify.

Ready means pending with eligible prerequisites; approval, valid worker inputs and the global execution slot still apply. Waiting means incomplete prerequisites or a task already in progress. Blocked means failed/cancelled/blocked task state, invalid success evidence or a blocked ancestor. Completed means successful evidence and eligible ancestors. These are derived classifications, never new mutable task states. Invalidating an ancestor affects descendants without rewriting their execution history.

Plan approval resolves validated plan keys to created task IDs and registers all edges in the same project/task/decision transaction. Any error rolls everything back. Revised plans still need a fresh fingerprint-bound approval. All generated tasks still require execution approval. Dependency edges are included in execution approval fingerprints; worker metadata changes also require a fresh approval.

Core execution checks prerequisites inside the existing BEGIN IMMEDIATE claim transaction, before consuming approval or creating an execution. Other database writers cannot change prerequisite evidence between that check and claim. Rejections append an audit event and create no execution. The single-worker safeguard remains. A second check under the final write transaction prevents recording success if prerequisite evidence became invalid while the worker ran.

The worker runs outside the database transaction. Evidence can change after claim; Orion does not preempt the worker or undo its output. A final invalidation marks the attempt failed and retains artifacts for review. Later invalidations change derived queue status, not historical records. Queue evaluation trusts persisted evidence and does not continuously rehash artifact files; use explicit verification to detect changed bytes. Recovery remains conservative and manual; no automatic retry, scheduling loop, parallel workers, dependency deletion or general research/engineering agents are implemented. Local database/code writers remain trusted operators, not a security boundary.


## Milestone 8: public technical research collection

`research-collect` uses Crossref's public works search and GitHub's public repository search. It runs as a trusted registered worker in the existing single-child execution engine. No model, API key, dependency installation or separate scheduler is needed. Schema 7 adds research_operations (pending-task configuration), research_runs (immutable per-execution configuration binding and write-once artifact digest), and immutable research_captures. Existing tables are preserved. Back up and run `init` before using the updated application; restart any running chat server to load new code.

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m orion init
$project = & $python -m orion projects create 'Technical research' | ConvertFrom-Json
$task = & $python -m orion tasks create 'Collect sources' --project $project.id --require-approval | ConvertFrom-Json
& $python -m orion research configure $task.id --question 'retrieval augmented generation' --crossref-limit 2 --github-limit 2 --request-budget 2 --no-include-readme
& $python -m orion research show $task.id
$request = & $python -m orion approvals request $task.id research-collect --reason 'Review bounded public API collection' | ConvertFrom-Json
& $python -m orion approvals get $request.id
& $python -m orion approvals decide $request.id approved --reason 'Reviewed question, providers and limits'
$run = & $python -m orion execute $task.id research-collect | ConvertFrom-Json
& $python -m orion history $task.id
& $python -m orion research packet $run.id
& $python -m orion verifications $run.id
& $python -m orion verify $run.id
```

Global `--database` and `--log-dir` still precede the command. `research show` takes a task ID; `research packet`, `verify` and `verifications` take an execution ID. Inspection never executes workers. A failed execution or verification returns CLI exit code 1 even when it also prints a structured result. Configuration is allowed only while pending; every configure call produces a new operation ID, invalidating old execution approvals. Changing question, providers, counts, budgets, byte limits, timeouts or README selection requires a fresh approval when the task is gated. Dependency checks still occur before claim and at finalization.

### Limits and request policy

Questions are nonempty and at most 256 UTF-8 bytes with no control characters. Provider selection is limited to crossref/github. Defaults: 3 search results per provider (maximum 5); 5 network requests total (maximum 8); 256 KiB per response (maximum 512 KiB); 5-second request timeout (maximum 10); 30-second worker timeout (range 5–60). Each source limit has its own CLI option. Research uses the configured worker timeout, also recorded in the approval proposal. Saved packets are capped at 8 MiB. Parent-side filesystem/verification work retains the existing engine's bounded-size but not separately hard-timed behavior.

Searches run first, once per enabled provider, before optional READMEs. README collection is enabled by default, uses only the fixed GitHub README API, accepts UTF-8 base64 file content up to 64 KiB and never fetches arbitrary download URLs. It stops at budget/deadline boundaries. Source-record names cannot contain path traversal components. Missing, invalid, oversized, budget-skipped and failed READMEs are explicit. Use `--no-include-readme` for the smallest smoke test.

Requests are unauthenticated HTTPS GETs to fixed api.crossref.org/api.github.com endpoints, with a descriptive User-Agent, explicit timeout, bounded read, content-type/status/JSON checks, no proxy inheritance and no redirects. Calls are sequential, at least one second apart within an operation. There are zero automatic retries. HTTP 403/429 conservatively stop subsequent requests to that provider for the operation; operators must respect provider cooldowns before starting a new operation. The application does not maintain a machine-wide rate-limit scheduler across independent databases. Provider/network errors are sanitized; remote error bodies are not printed. A child that exceeds the execution timeout is terminated under existing engine rules; partial in-memory responses may be lost on a hard timeout or crash.

### Evidence and completion policy

Packets contain operation/execution IDs, question/configuration, creation and retrieval timestamps, provider outcomes/counts, records, raw captured JSON responses, capture/evidence digests and limitations. Every record references an exact capture index and source-result index. Native metadata is preserved without inventing missing values: Crossref title/author/issued.date-parts/DOI/publisher/container-title/abstract/URL; GitHub owner/name/description/language/html_url/default_branch/stargazers_count/forks_count/updated_at. Crossref year remains in its native issued date-parts representation. Evidence contains the returned title/abstract or description and optional decoded README; metadata is not represented as paper full text. Missing fields are listed. Abstract markup is retained as untrusted text.

Stable identities use DOI (case-folded), GitHub numeric repository ID, or a canonical metadata hash when Crossref supplies no DOI. Missing publication URLs fall back to the discovery API URL and missing metadata remains visible. Duplicate identities within a provider use the first returned record consistently; returned_count and record_count expose deduplication. Each evidence digest hashes canonical JSON of the original metadata plus evidence content. Retrieval timestamps describe collection, not independent source authentication.

Partial provider failure preserves successful records and failure details. A packet can pass structural/provenance verification while documenting an outage. At least one successful provider search is required for task success; an empty successful search may legitimately complete with zero records. If all providers fail, the engine saves/verifies the failure packet but marks execution failed. Results are bounded search samples, not exhaustive literature reviews. Popularity is not a quality/security/maintenance assessment.

The independent research verifier does not call the collector, its connectors or worker validator and performs no network requests. It rereads managed artifact bytes, checks the original artifact digest and operation/capture bindings, independently checks provider envelopes, selected records, first-occurrence deduplication, exact metadata/evidence, source URLs, query/time attribution, README references, failures/counts and canonical evidence digests. Verification records use the existing immutable table and events. A later failed verification blocks downstream dependencies without rewriting a past successful execution. This checks internal provenance against responses captured by trusted local code; it does not certify factual correctness, current source availability, cryptographically authenticate the provider's statements or defend against a malicious local database/code writer.

The CEO planning context now describes research-collect. The existing plan schema can propose a task with a question and acceptance criteria; approving that plan creates approval-required tasks. An operator then configures the research task and approves its exact execution. No research tool is exposed to the chatbot, no source text is fed into a model here, and no real-model planning capability is claimed. Future synthesis must be a separate dependent task, with external text treated as untrusted evidence.

Reference documentation: [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), [GitHub repository search](https://docs.github.com/en/rest/search/search#search-repositories), [GitHub README API](https://docs.github.com/en/rest/repos/contents#get-a-repository-readme). These sources describe the metadata endpoints; a valid API response does not establish source correctness.


## Milestone 9: research synthesis

`research-synthesize` consumes a successful, currently eligible `research-collect` execution in the same project. It never accepts a source path. Selection reads the managed UUID artifact, verifies its original SHA-256, configuration/capture digests and provenance structure, and requires the latest matching passed research verification. The selected attempt must be the research task's latest eligible execution; missing/failed/tampered evidence is refused. The original packet is never replaced.

Schema 8 adds only synthesis_operations (task configuration) and synthesis_runs (immutable execution binding with write-once output digest). Existing executions, ownership, events, artifacts, verification records and inference_claim are reused. Back up the database and run `init`; restart a running chat process to load current code. Configuration adds the research task as a dependency and permanently enables execution approval. Reconfiguration preserves old dependencies conservatively; there is no implicit edge deletion.

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m orion init
# Use the project and execution IDs returned by a completed research collection.
$task = & $python -m orion tasks create 'Analyse research evidence' --project <PROJECT_ID> | ConvertFrom-Json
& $python -m orion synthesis configure $task.id --source-execution <RESEARCH_EXECUTION_ID>
& $python -m orion synthesis evidence $task.id
& $python -m orion synthesis show $task.id
$request = & $python -m orion approvals request $task.id research-synthesize --reason 'Review source, excerpts, model and limits' | ConvertFrom-Json
& $python -m orion approvals get $request.id
& $python -m orion approvals decide $request.id approved --reason 'Reviewed exact synthesis operation'
$run = & $python -m orion execute $task.id research-synthesize | ConvertFrom-Json
& $python -m orion synthesis summary $run.id
& $python -m orion synthesis packet $run.id
& $python -m orion verifications $run.id
& $python -m orion history $task.id
& $python -m orion verify $run.id
```

`show` and `evidence` are task-ID read-only inspections of the selected input, evidence digest, latest verification ID, current configured model and bounded projection. They refuse invalid upstream evidence. `packet` and `summary` take a synthesis execution ID; summary shows actual execution/provider outcome, findings, recommendation or refusal, references, warnings, limitations and verification history. Inspection does not invoke a model. `verify` explicitly appends an independent verification record. Failed execute/verify commands print their structured result and return exit code 1.

### Provider and concurrency

The existing Provider.chat(messages, schema) protocol and OllamaProvider adapter are reused. One create_provider factory serves chat and synthesis; the existing configuration currently supports only Ollama. Synthesis business logic uses the protocol and does not implement another HTTP client or automatically substitute fixtures. Model, provider, endpoint, timeout, context and output settings come from AIConfig/ORION_AI_* and are included in approval fingerprints along with source execution, evidence digest, verification ID, source projection and synthesis parameters. Changing them invalidates old approvals. A mutable local model tag is not a cryptographic model-weight identity; actual returned model/provider are also recorded.

Synthesis claims the existing database-wide inference slot under the execution claim transaction. Chat and synthesis cannot overlap within that database. The worker uses the existing spawned-child timeout (default and maximum 60 seconds for synthesis; configurable 5–60). AIConfig's provider timeout can be longer; the worker deadline takes precedence and may terminate the client while server inference continues. Prefer an explicitly configured provider timeout shorter than the worker deadline when testing. Unknown failures, provider uncertainty and hard timeouts retain the inference claim. Inspect ai-status, stop/restart the model service, resolve any running execution conservatively, then use the existing `ai-reset --confirm-service-restarted --reason TEXT`. Reset refuses while synthesis is running. Separate databases do not share the inference lock; do not use them to run concurrent model workloads. No model is installed/downloaded and no provider fallback is automatic.

### Prompt and analysis contract

Defaults: all source records, maximum 10; leading 800 characters per evidence field (80–2000 configurable); 12000 total UTF-8 prompt bytes (2000–20000 configurable), further capped at twice configured context size; 16000 output bytes (1000–16000 configurable). The prompt budget includes messages and JSON schema. This byte heuristic is not exact tokenization and cannot guarantee every model's context behavior. Too many records or oversized prompts are rejected; no records are silently dropped. Reduce excerpt_chars explicitly if needed. Selected metadata fields, all source IDs, provider outcomes and known limitations are included; each shortened evidence field records original/included character counts. The prompt explicitly states it contains selected metadata and excerpts, not full papers or complete READMEs. Unrelated conversations, environment variables, credentials and arbitrary files are never supplied.

The model receives a system instruction plus a JSON evidence message. Source content is untrusted data, never tools or permission changes. The model has no tool interface and no database/filesystem/shell capability. Prompt injection can still distort prose; local validation cannot guarantee semantic obedience or reasoning quality.

Analysis is exact-field JSON: schema_version, execution_id, question, executive_summary, key_findings, comparisons, advantages, disadvantages, evidence_limitations, unresolved_questions, recommendation, next_experiments and confidence. Claim objects contain text and source_ids. Text is bounded to 1200 characters per field; each list has at most 8 entries and references at most 10 unique IDs. Confidence is low/medium/high with an explanation. Unknown fields, duplicate keys, nonfinite JSON, wrong types, excessive lists and mismatched execution/question are rejected. A recommendation can explicitly be unsupported with a reason and empty references. With zero sources, factual claim lists must be empty and no supported recommendation is allowed.

### Citations, persistence and independent verification

Every summary/finding/comparison/advantage/disadvantage and supported recommendation requires actual input source IDs. The only summary exception is a no-evidence summary when no records exist. Limitations, unresolved questions, confidence explanation and proposed experiments are designated non-claim fields and need no external citations. Humans must detect factual claims improperly placed in those fields; a deterministic validator cannot reliably classify arbitrary prose. Withheld recommendation text must explain insufficiency, not introduce uncited factual claims.

Reference validation is a separate deterministic step. IDs resolve to original source URLs, provider, evidence digest and evidence kinds. Cited records with fewer than 80 characters of non-title evidence receive a sparse-evidence warning. This heuristic identifies thin evidence, not semantic support. Citations do not prove entailment, correctness, source quality or recommendation suitability. No model-generated URL substitutes for an input ID.

The separate artifact envelope records upstream execution/digest, worker version, configured model, actual response metadata, timestamp and raw model response text. Invalid model JSON and unknown references remain inspectable in a failed artifact. Oversized provider output is rejected without retaining the oversized body. Provider errors save an error envelope when possible; hard process crashes/timeouts may leave no artifact. The source packet remains unchanged.

The independent verifier does not call the worker, worker validator or model. It rereads the saved envelope and current eligible upstream packet, rechecks both digests and projection, parses the raw response against the shared declarative schema, and independently runs source resolution/citation policy. It persists passed/failed results in the existing immutable verifications table as synthesis-independent. Research and synthesis verification histories remain separate. The engine also rechecks upstream eligibility/digest before finalization. Later invalidation blocks derived downstream readiness without rewriting historical execution records. Structural/provenance verification is not factual certification.

Ordinary automated tests use explicitly named fixture providers and local HTTP fixtures. A successful fixture is not AI analysis. Real-model output quality, schema compliance and latency still require a separate installed-model integration test and human review. There is no synthesis-to-execution automation.

## M10 Stage 1 — Offline intelligence evaluation

Added packet-specific allowed source IDs to research synthesis output constraints and strengthened general planning guidance for dependency completeness, integration, testing, measurable acceptance criteria, and hardware resource distinctions. The offline 16-case evaluation set and results are documented in [reports/M10_OFFLINE_EVALUATION_REPORT.md](reports/M10_OFFLINE_EVALUATION_REPORT.md). The full test suite passes 121 tests. No live model inference was run in this stage.
