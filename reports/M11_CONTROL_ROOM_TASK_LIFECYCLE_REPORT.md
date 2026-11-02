# M11 — Worker assignment and execution through Control Room

Date: 2026-10-31. Repository: `C:\Users\JEFFIN\Projects\orion`.

## Result

The Control Room can now bind a registered worker to a pending task, configure its supported operation, preview the backend proposal, request approval, inspect and decide the request, explicitly start an approved execution, monitor recorded execution state, and inspect saved output and verification history. Task creation continues through the existing project/task service. Creating, assigning, configuring or approving a task never automatically starts it.

The acceptance task remains unassigned and unexecuted because no registered worker performs browser/UI acceptance testing. This is a real capability gap, not a successful worker acceptance run. No live model or research collection was invoked.

## Inspection and architecture

Reviewed the actual worker registry, project/task service, approval proposal/fingerprint generation, dependency service, execution claims and ownership, inference claim, existing input/research/synthesis configuration services, independent verification, and Control Room routes and assets.

Worker assignment is an append-only `worker_assigned` event in the existing event table. No new table or schema migration was needed; schema version remains 8. Each binding records worker identifier, version and event ID. Invalid workers and nonpending task assignments are rejected. Repeating an unchanged binding does not create a new event. Reassigning A to B to A creates a distinct binding and invalidates old proposals.

`ApprovalService.proposal` checks explicit assignment and includes its immutable event identity in the existing fingerprint. Legacy unassigned proposals retain their prior shape. Request creation accepts an optional expected fingerprint and revalidates it inside the original write transaction. The existing execution engine still authorizes the operation, consumes approval, checks dependencies, obtains the exclusive execution claim, runs its worker subprocess, records history/artifacts and invokes the applicable independent verifier. No second authorization or execution framework was added.

## Registered workers and configuration

| Worker | Actual operation and configuration |
|---|---|
| `project-status` v1 | Project/task snapshot report. No extra configuration. Does not inspect a browser or implement software. |
| `csv-profile` v1 | Profile an already imported managed CSV input ID using the existing bounded CSV limits. |
| `research-collect` v1 | Bounded Crossref/GitHub collection using the existing question, providers, README and resource-limit configuration. Actual execution uses HTTPS. |
| `research-synthesize` v1 | Analyze an actual verified upstream research execution using existing synthesis limits and optional exact passage selections. Actual execution invokes the configured provider. |

The catalog uses actual registry descriptions and existing configuration defaults/bounds. It distinguishes registration from input readiness, provider availability and execution readiness. The JSON configuration editor delegates validation to the original input, research and synthesis services; unsupported fields fail there. CSV input inspection lists registered managed IDs. Importing a new local CSV still uses the existing CLI import procedure.

## Browser lifecycle and APIs

Task detail now contains overview, assigned worker and capabilities, dependencies/readiness, supported configuration, approval history, execution history/output/verification, and a timeline derived from actual creation time and events. Scheduling classifications, approval states and execution states are labeled separately; no synthetic database task states were introduced.

New read routes: `/api/worker-catalog`, `/api/inputs`, `/api/task-preview`, `/api/artifact`.

New write routes: `/api/task-assignment`, `/api/task-configuration`, `/api/task-approval`, `/api/task-execute`.

Preview generates the exact proposal and fingerprint on the backend. A short-lived, single-use server-held token binds approval request creation to that preview; client-supplied proposal bodies are never trusted. The existing approval confirmation and decision flow displays the stored proposal before an explicit approve/reject decision. Freshness is validated against the original backend fingerprint. Assignment, task/project snapshots, dependencies, inputs and existing synthesis/provider configuration continue to participate in proposal checks.

The Execute flow re-fetches current task eligibility, displays the approved exact operation, and requires a separate explicit action. POST execution requires the existing request identifier deduplication mechanism. A double submission cannot create a second attempt: request replay returns the recorded response, and the execution engine independently enforces its durable claim and consumed approval. The existing threaded HTTP handler waits for the execution service; the browser polls read-only task history while that request is pending. There is no automatic retry, fallback, scheduler or downstream task execution.

Saved artifacts are located by validated execution ID under Orion's managed artifact directory after worker ownership is stopped. Browser inspection accepts no arbitrary filesystem path. Artifact display does not replace independent verification. Project-status snapshot validation is identified separately from CSV/research/synthesis independent verification.

## Security and preservation

Existing loopback Host/Origin checks, CSRF token, bounded JSON handling, short-lived confirmation tokens, HTML escaping and request deduplication remain in use. Worker selection uses registry identifiers. Configuration is checked by existing services. Provider credentials never become worker configuration fields or browser settings. No provider code, model behavior, verifier contract, recovery procedure or approval consumption rules were weakened.

Before/after SHA-256 comparisons cover 26 protected files: existing SQLite databases/backups, saved research/report artifacts, the selected-passage preview, Groq/provider/Ollama/synthesis worker source, Groq tests and independent synthesis verifier. All 26 matched after implementation, tests and browser inspection. The original isolated validation database and research evidence were not modified.

Read-only final checks of `data/m10-stage3-retry/validation.sqlite3` confirmed:

- Execution `21a04b45-f0bd-4cac-a91f-1e2a76ff9977` is still `failed` with its original EOF failure evidence.
- Approval `4e502cb1-c761-4f57-8072-c2e2de5ee549` is still approved but consumed by that execution.
- Its inference claim still exists with `uncertain = 1` and the same execution token.
- Zero running executions are recorded. No ai-reset, Ollama restart, recovery, new approval or inference was performed in that database.

The idle Control Room development server was restarted to load the updated backend at `http://127.0.0.1:8765/`. Ollama was untouched. Existing Stage 5.1/5.1.1 working changes and prior untracked reports/assets/tests were retained.

## First acceptance task

Retrieved from the actual application database, `data/orion.sqlite3`:

- Project: `a4370839-16c0-4ddc-aa46-fc0a5f0b77af` — AI Company Control Room.
- Task: `84be5109-2f00-4834-8fba-dae5d902640e` — Orion Control Room — First Acceptance Test.
- Stored state: `pending`, priority 20; approval required; no prerequisite recorded.
- Requested work: functional review of dashboard, project data, task creation/inspection, workers, approvals, execution history and navigation.

No existing worker meaningfully performs this UI review. Project-status only summarizes database records; CSV profiling and research operations have different input/output contracts. Consequently no worker was assigned, no execution proposal/approval was created and no execution was started for this task. Final queries found only its original `approval_required` event and zero task approvals/executions. “Ready” scheduling classification means prerequisites are satisfied; it does not grant approval or establish a suitable worker.

The real browser was reloaded and navigated through Task Management into this task. Its four actual worker choices, lifecycle sections, pending/unassigned state, empty histories, and lack of an Execute action were confirmed. No mutation controls were submitted. A screenshot is saved locally in `data/m11/task-lifecycle.png`. An additional read-only renderer check against live GET responses confirmed the lifecycle sections and absence of execution authority.

## Actual tests

| Check | Result |
|---|---|
| Existing Control Room tests before lifecycle additions | 13 passed |
| New lifecycle tests | 15 passed, 0 failed, 0 skipped; 4.302 seconds |
| Complete regression suite | 192 passed, 0 failed, 0 skipped; 114.324 seconds |
| Existing Control Room tests after final unassigned-configuration display copy change | 13 passed, 0 failed, 0 skipped; 2.895 seconds |
| JavaScript syntax | `node --check src/orion/control-room.js` passed |
| Tracked whitespace check | `git diff --check` passed; Git emitted only an existing LF/CRLF conversion notice |

Full regression command: `.venv\Scripts\python.exe -m unittest discover -s tests`.

The 15 new tests use disposable temporary SQLite databases and exercise actual HTTP/service boundaries: registry-only catalog, invalid/persistent assignment, unchanged-binding reuse, schema version preservation, supported config validation, expected binding identity, exact preview/request/decision/execute/artifact lifecycle, missing approval, request-ID requirement, duplicate submission, direct-service wrong-worker rejection, stale previews and replay, reassignment invalidation, dependency enforcement, managed CSV profiling with independent verification, research config validation, verified synthesis upstream selection, uncertain inference gating, managed artifact path rejection, read-only GET behavior, and fixture synthesis through the unchanged independent verifier. Test provider/network fixtures are deterministic and explicitly isolated from production. They are not evidence of actual model quality or hosted API compatibility.

The complete suite ran before the final text-only replacement of an unassigned configuration `null` with an explanatory sentence. After that change, JavaScript syntax, existing Control Room tests and the actual rendered browser view were checked. Test logs are local ignored files in `data/m11/`.

## Files and Git state

M11 additions: `src/orion/task_workers.py`, `src/orion/task_lifecycle.py`, `tests/test_task_lifecycle.py`, and this report.

M11 edits to existing working files: `src/orion/approvals.py`, `src/orion/control_room.py`, `src/orion/web_chat.py`, `src/orion/control-room.js`.

The working tree intentionally retains all prior uncommitted provider/Control Room changes. At final inspection, tracked modifications were `pyproject.toml`, `src/orion/approvals.py`, `src/orion/chat.html`, `src/orion/execution.py`, `src/orion/ollama.py`, `src/orion/provider.py`, `src/orion/synthesis_worker.py`, and `src/orion/web_chat.py`. Untracked source/assets/tests/reports include the previous Groq and Control Room work plus the M11 additions. Nothing was staged or committed; the staged diff is empty. HEAD remains `917705854831fe248eca0a7234855592a46b131d`. No push was made.

## Readiness and limitations

The supported registered-worker lifecycle is implemented and regression-tested. Open Task Management, choose a task, select a suitable worker, save supported configuration, preview/request approval, inspect and decide it in Approval Centre, return to the task, review its approved operation and explicitly execute it. Existing claim/recovery rules can block execution independently of browser readiness.

Actual research collection and model inference were not exercised in the application database. The first acceptance task needs human UI review or a separately scoped browser-testing worker before it has a suitable executable assignment. This milestone does not add that worker or represent a database status report as browser testing. The current implementation requires the browser to remain open for live monitoring; durable records remain inspectable after navigation/restart. Failed/uncertain inference recovery remains a separate administrative procedure requiring its own authorization.
