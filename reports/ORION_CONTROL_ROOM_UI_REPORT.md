# Orion AI Company Control Room — frontend and integration report

2026-10-31, Asia/Calcutta. Implemented against the existing Python/SQLite application. All prior Stage 5.1 and Stage 5.1.1 working changes and untracked reports were preserved. HEAD remains `917705854831fe248eca0a7234855592a46b131d`; no commit or push was made.

## Architecture inspected

The original `web_chat.py` served one inline HTML chat page through a loopback `ThreadingHTTPServer`. Its routes already used `ConversationService` and `PlanService`. POSTs required an exact loopback Host, same Origin and a random per-server request token. The existing SQLite schema is version 8. The provider protocol, worker registry, project/task service, dependency explanations, execution/verification services, approval proposal hashing, managed research packets and synthesis artifacts were inspected before implementation.

There are four registered workers in the current source: project-status, csv-profile, research-collect and research-synthesize. A task has no dedicated assignment column, so the UI's worker binding derives from its configured operation or latest actual execution. Scheduling readiness is displayed separately from stored task status. No database schema migration or new dependency was required.

## Design and completed screens

The interface uses charcoal panels, restrained cyan/blue accents, system fonts, a responsive sidebar, clear status labels, compact tables and on-demand detail dialogs. The desktop dashboard uses real summary cards, a recent-execution table, provider configuration and event activity. Mobile uses a collapsible navigation menu and a single-column workspace. Motion honors reduced-motion preferences.

| Screen | Actual behavior |
|---|---|
| Dashboard | Queries project/task/execution totals, stored pending approvals, execution outcome counts, latest eight attempts and latest twelve recorded events. Configuration is labeled separately from reachability and loaded state |
| CEO Chat | Lists and selects existing conversations, creates a conversation with optional project context, sends through `ConversationService`, shows saved messages and model/system labels, displays in-flight feedback and provider errors, retains failed input, and reviews structured plans through `PlanService` |
| Projects | Real name/description/status/creation time and task counts. Completion ratio uses actual completed tasks. Project creation delegates to `Service.create_project`; opening a project filters its actual tasks |
| Task Management | Project filter, task creation, worker binding, state, priority, dependencies and execution history. New UI-created tasks require approval. Detail shows dependency classification without inventing a stored ready/waiting state |
| Worker Department | Actual registry names, identifiers, versions, responsibilities, capabilities, verifier and input/output expectations. Registration is distinguished from a live process |
| Approval Centre | Lists up to 200 historical and pending requests, including consumed and rejected records. Inspection shows exact proposal JSON, task, worker, fingerprint and freshness. Current pending requests can receive a reason and a second confirmation before backend approval/rejection |
| Research Department | Lists configured collections with queries/providers and synthesis tasks with upstream execution links. Managed evidence dialogs show source IDs, URLs, captured records, provider outcomes and verification history. Saved synthesis operation/projection and report inspection remain separate from collection evidence |
| Execution History | Latest 200 attempts, actual IDs, worker/task/status/attempt/timestamps, recorded errors and verification history. Research/synthesis executions link to their managed report |
| System Settings | Safe provider/model/endpoint/context/output/timeout/temperature inspection. Explicit read-only provider check distinguishes reachable, configured and loaded. Hosted configuration leaves account entitlement unverified |

Ordinary navigation and record inspection work without a terminal after startup. Project/task and conversation creation are functional. Every visible action is connected to a real route or normal browser dialog/navigation action. Empty states use the selected database's actual contents.

## Backend routes

Reused conversation routes `/api/conversations`, `/api/conversation`, `/api/message` and the plan decision route `/api/decision`. Reused `/api/projects` now includes computed task progress. `/api/status` retains provider availability behavior and adds a read-only Ollama `/api/ps` check when the local service is reachable. These status checks do not load models. A Groq configuration check remains local and does not validate the hosted account.

Added GET routes `/api/overview`, `/api/workers`, `/api/tasks`, `/api/task`, `/api/executions`, `/api/execution`, `/api/approvals`, `/api/approval`, `/api/research` and `/api/evidence`. Added POST routes `/api/projects` and `/api/tasks` for existing safe service operations. Added `/api/approval-confirmation` and `/api/approval-decision` for two-step CEO decisions. Static CSS and JavaScript are served only from two explicit names; arbitrary file paths are unavailable.

`ControlRoom` owns read-model queries and delegates record/managed-artifact operations to existing services. The HTTP handler retains the conversation and plan engines. It exposes no worker-execute, synthesis-configuration, inference-reset, arbitrary shell or arbitrary URL-fetch route.

## Approval and request security

The browser submits an approval ID, intended decision and reason for inspection. The server rechecks proposal freshness and issues a random single-use confirmation lasting 180 seconds. The confirmation holds the server's actual fingerprint and exact decision/reason. The browser then submits only this confirmation token. A second dialog displays the full proposed operation before this final submission.

`ApprovalService.decide` gained an optional `expected_fingerprint` parameter. For this confirmed UI path, it checks pending/unconsumed state, current task state and a freshly generated proposal inside the same write transaction as the existing decision update. Existing callers retain their prior signature and behavior. A stale proposal or changed task cannot be approved using an old confirmation. Consumed/already decided requests expose inspection only. This approval records a decision; the UI does not automatically execute anything.

POSTs retain exact Host, Origin and CSRF-token enforcement. Client-generated request IDs deduplicate submissions for ten minutes within the server process; cached results return the original object and concurrent/mismatched reuse is rejected. Confirmation and deduplication caches are bounded. Buttons are disabled during requests, and forms validate locally and server-side. An application restart clears these in-memory caches and confirmations; persistent approval decision rules still prevent repeat decisions.

JSON output masks an exact configured Groq credential if it occurs in returned record text or an error. The browser receives safe configuration values, never the environment variable or Authorization header. Provider calls remain server-side. JSON/record text is escaped before rendering; source links allow only HTTP(S), open with noreferrer/noopener and do not pass through a backend fetcher. CSP uses a per-server script nonce, frame restrictions and same-origin styles. Database/file errors produce controlled responses, and missing records return appropriate errors.

The existing security model is a local trusted-operator interface with origin/token protections. It is not a multi-user authenticated deployment. The server binds only `127.0.0.1`; no external interface or hosted deployment was added.

## Tests and visual verification

Added 13 actual local HTTP integration tests with isolated temporary SQLite databases and explicit fixture providers. They cover dashboard/static responses, project/task creation/retrieval, project progress, request deduplication, conversation service integration, approval inspection/confirmation/expiration/replay, stale-decision rejection, rejected and consumed records, execution history, worker registry, collected research artifacts and verification, read-only GET behavior, Host/Origin/token enforcement, invalid and missing records, and credential masking.

Targeted control-room run passed **13 tests in 2.096 seconds**. The first full regression run discovered one failure in an existing initial-HTML assertion for “Propose plan”, because chat controls are now rendered by JavaScript. Added a useful no-JavaScript instruction to the initial page and preserved that original test. The chat suite then passed **13 tests in 2.031 seconds**.

Final full command `.\.venv\Scripts\python.exe -m unittest discover -s tests -q` passed **177 tests, zero failures and zero skips, in 109.281 seconds**. This retains all 164 previous tests and adds 13 control-room tests. The final log is `data/control-room/full-tests-final.txt`. Existing tests were preserved without weakening assertions.

Manual inspection used the actual application and default `data/orion.sqlite3`, which currently contains three projects, four tasks and three executions. All nine sections rendered using those real records. Project navigation opened its actual tasks, and task detail displayed dependency classification and recorded execution history. CEO Chat displayed an existing conversation and its historical provider error; no new model request was sent.

The default database currently has no configured research collections, so the Research Department correctly displays an empty state. Research artifact/verification routes were exercised through the isolated HTTP integration tests. The historical richer evidence remains in the separate Stage 3.1 validation database. There was no database switching or mutation of that history during browser testing. Confirmation decisions and chat submissions were tested using fixtures; production browser inspection remained read-only.

The browser console contained zero captured warnings or errors during the desktop navigation checks. Responsive inspection used a 390×844 viewport, verified the mobile navigation toggle and chat layout, and found no document-level horizontal overflow. The temporary viewport override was reset. Screenshots are retained in ignored `data/control-room/desktop.png` and `data/control-room/mobile.png`. They show real default-workspace records. The mobile screenshot captures the dashboard; chat was additionally inspected visually.

## Files changed for this UI milestone

| File | Purpose |
|---|---|
| `src/orion/chat.html` | Control-room shell, navigation structure, accessible dialogs and script nonce |
| `src/orion/control-room.css` | Responsive visual design |
| `src/orion/control-room.js` | Real section rendering, navigation, dialogs and guarded API actions |
| `src/orion/control_room.py` | Dashboard and inspection read models using existing services |
| `src/orion/web_chat.py` | Minimal new HTTP routes, static assets, request deduplication and confirmation exchange |
| `src/orion/approvals.py` | Optional atomic fingerprint check for confirmed browser decisions |
| `pyproject.toml` | Includes the new static assets in the installed package |
| `tests/test_control_room.py` | HTTP/service security and regression coverage |
| This report | Implementation, validation and operating instructions |

The existing uncommitted Groq implementation/review files retain their exact pre-UI hashes, including earlier modifications in `provider.py`, `ollama.py`, `synthesis_worker.py`, `execution.py`, and `test_groq.py`. The independent synthesis verifier, old failed run, consumed approval, uncertain claim, original evidence and selected passages were protected. Preservation checks compare 27 pre-existing work/database/artifact paths with their entry hashes.

## Resource considerations and remaining scope

The application has no frontend build system, third-party scripts, CDN font, framework, database replacement or extra inference worker. HTML/CSS/JavaScript total about 40 KiB. Views load on demand, with manual refresh rather than polling. Evidence and operation details are retrieved only when requested. One existing server entry point serves both UI and API. A server process snapshot showed approximately 18.0 MiB working set plus a 3.8 MiB launcher; this is a momentary process measurement, not a peak or browser-memory guarantee.

New research/synthesis configuration and worker execution remain the existing CLI workflow. Provider editing and uncertain-state recovery are deliberately absent from browser controls pending a validated security-sensitive workflow. Worker departments beyond the actual registry and a persisted human-reviewed-conclusion state remain future capabilities. Hosted API entitlement and real model analytical quality remain subjects for separately authorized validation. The UI adds no claim that these are complete.

## Startup and exact address

From `C:\Users\JEFFIN\Projects\orion`, use the existing environment and entry point:

```powershell
.\.venv\Scripts\python.exe -m orion chat --port 8765
```

Open **http://127.0.0.1:8765/**. Use that exact loopback address because the server validates Host and Origin. The default workspace is `data/orion.sqlite3`; records in separate validation databases do not appear in that workspace. When choosing another existing workspace at startup, the CLI's `--database` option precedes `chat`. The selected database must already be initialized and healthy. Do not use a protected historical database for new mutations without explicit authorization.

At completion one control-room server is running on the existing application entry point for the default workspace. No live inference, model loading, new synthesis operation, approval consumption, claim reset or recovery occurred during development. Fixture mutations were confined to temporary test databases. All work remains uncommitted and unpushed for CEO review.
