# M10 Stage 5.1 — Groq hosted inference adapter, offline implementation

2026-10-31, Asia/Calcutta. Implementation and deterministic HTTP-mock tests completed. Hosted access, account entitlement and model quality require separate live validation.

## Baseline and inspection

Repository `C:\Users\JEFFIN\Projects\orion`, branch `main`, initial HEAD `917705854831fe248eca0a7234855592a46b131d`. The pre-existing untracked Stage 3.4 report was preserved separately. Baseline full suite ran before source edits and passed **136 tests, zero failures or skips, 110.354 seconds**.

Inspected provider/configuration/factory, Ollama transport, synthesis configuration and compact schema, worker, execution engine, approval proposal/fingerprint, independent synthesis verifier, conversation/context/plan schema, database/event/logging conventions, packaging and Git exclusions. Existing tests inspected included `test_chat.py`, `test_synthesis.py`, `test_passages.py`, `test_research.py` and `test_foundation.py`. There are no added dependencies or migrations.

## Files changed

| File | Change |
|---|---|
| `src/orion/provider.py` | Groq fixed-endpoint configuration and factory, explicit model selection, temperature configuration, optional numeric response usage, categorized provider errors |
| `src/orion/groq.py` | New bounded HTTPS adapter with strict schema requests, deadline, sanitized error mapping and numeric usage extraction |
| `src/orion/ollama.py` | Uses configured temperature, retaining its previous 0.2 default |
| `src/orion/synthesis_worker.py` | Forwards optional usage to the engine through a transport-only field |
| `src/orion/execution.py` | Removes that transport field before publication and stores usage as an execution event |
| `tests/test_groq.py` | 24 new deterministic tests, including isolated engine/approval/verification fixtures |
| This report | Implementation, test and security findings |

The existing independent verifier, synthesis output schema, passage projection, research collection and approval-control implementations have no edits. Existing callers can still construct the four-argument `Response`; optional usage defaults to null. Previously stored configurations can still be loaded because the added temperature defaults to 0.2. Newly generated approval fingerprints include temperature explicitly, so older unused proposals can require fresh approval. Immutable historic snapshots retain their original values.

## Configuration and credentials

`create_provider(AIConfig.load())` selects Ollama or Groq. Groq requires an explicit `ORION_AI_MODEL`. Configuration selects the fixed `https://api.groq.com/openai/v1/chat/completions` endpoint by default for Groq, and rejects every other Groq endpoint, including alternate paths, query strings or HTTP. Existing Ollama endpoints retain loopback restrictions.

Configuration names are `ORION_AI_PROVIDER`, `ORION_AI_ENDPOINT`, `ORION_AI_MODEL`, `ORION_AI_CONTEXT`, `ORION_AI_MAX_OUTPUT`, `ORION_AI_TIMEOUT`, and `ORION_AI_TEMPERATURE`. Temperature is finite and bounded 0–2, default 0.2. Existing context/output/timeout bounds remain enforced. Per-request wire settings are the explicit model, configured temperature and maximum completion tokens, one choice, and streaming disabled. Schema calls use fixed strict mode. No tools or searches are requested.

The credential is read from `ORION_GROQ_API_KEY` only when making the authorized request. It belongs solely in the Authorization header. It is absent from `AIConfig`, serialized operations and approval fingerprints. Tests rotate synthetic credentials and confirm equal fingerprints and absence from SQLite bytes. Missing or invalid key errors use fixed messages. Response bodies and exception messages from the HTTP library are excluded from diagnostics. Echoed credential material in response bytes or request content causes rejection.

The stdlib HTTPS connection uses `ssl.create_default_context()` with certificate and hostname verification. It makes a single direct request with no redirect following, proxy discovery, SDK retry, provider fallback or account/model-listing preflight. `availability()` reports configuration readiness and explicitly leaves remote service access unverified.

The serialized configuration binds provider, model, fixed endpoint, context budget, output bound, timeout and temperature through the existing operation/proposal fingerprint. One-request/strict-mode behavior is fixed in the adapter. The host model context cannot be set using Ollama's `num_ctx` on Groq. Orion's context value remains an application prompt-budget parameter. Its byte/token heuristic has not become a hosted tokenizer guarantee.

## Structured-output compatibility

Groq's current documentation lists strict mode for `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b` and `meta-models/muse-spark-open`. The adapter records this reviewed capability set and rejects schema calls for other models before connecting. These names establish documented capabilities. Free-tier availability and account permissions remain unverified. [Supported models](https://console.groq.com/docs/structured-outputs#supported-models)

Strict mode requires all object properties to be required and every object to specify `additionalProperties: false`. Orion meets those structural rules. Groq also documents `$defs`, `$ref`, enums and nested arrays/objects. The adapter checks the structural rules and transmits Orion's schema exactly, including source-ID enums, string bounds, list bounds and unique-reference rules. It performs no conversion to JSON-object mode or relaxed schema. The compact schema is tested for unchanged bounds, enums and definitions in the mocked payload. [Schema requirements](https://console.groq.com/docs/structured-outputs#schema-requirements)

The documentation does not separately spell out support for Orion's `minLength`, `maxLength`, `maxItems` and `uniqueItems` keywords. Consequently, actual server acceptance of the full contract is an explicit live-test question. No incompatibility was established offline, and no keyword was removed. A server rejection remains an unsupported-request failure. A confirmed incompatibility must be resolved before further inference, without relaxing Orion's contract. Every accepted synthesis still goes through local schema/citation/provenance validation and the original independent verifier.

## Errors, timing and persistence

| Condition | Error code / behavior |
|---|---|
| Missing or invalid environment credential | `missing_key`, before transport |
| Unreviewed schema model | `unsupported_model`, before transport |
| Open or optional object fields | `unsupported_schema`, before transport |
| HTTP 401 / 403 | `authentication`, with HTTP status |
| HTTP 429 | `rate_limit`, with normalized Retry-After seconds when parseable |
| HTTP 400 / 404 / 422 | `unsupported_request`, preserving status and withholding untrusted response text |
| HTTP 5xx | `server_failure`, outcome conservatively uncertain |
| Other HTTP status, including redirect | `http_error`, no follow-up request |
| Timeout / connection failure | `timeout` / `connection_failure`, outcome conservatively uncertain |
| Invalid JSON, choice shape, role, tools or invalid usage | `malformed_response` |
| Refusal / missing content / incomplete finish | `refusal` / `missing_content` / `incomplete_response` |
| Unexpected returned model | `model_mismatch` |
| Oversized request, response or content | Explicit size error; maximum request 64 KiB, response 128 KiB, content 16,000 UTF-8 bytes |
| Credential reflected in content | `credential_exposure`, response discarded |

Retry-After accepts delta seconds and HTTP dates. The sanitized error carries the normalized wait requirement for a separately authorized attempt. HTTP error bodies are discarded. No automatic retries occur. An interrupted request may still be active remotely, so uncertainty remains governed by Orion's existing inference slot. This stage adds no hosted cancellation or reset procedure.

Latency measures one request from connection setup to complete response, using monotonic time. Numeric prompt/completion/total tokens and queue/prompt/completion/total provider timings are retained when present. Arbitrary provider usage fields are discarded. The engine stores these metrics in the append-only `synthesis_provider_usage` event tied to the execution. The saved synthesis envelope keeps its original three-field response metadata and exact output contract, so the independent verifier requires no modifications. Plain chat callers receive usage through the provider `Response`; the existing conversation-message table retains its existing latency metadata.

## Tests executed

Added 24 tests using mocked HTTPS transport and isolated temporary databases. New collection fixtures substitute captured-shaped records in memory without sockets. Spawned synthesis fixture workers call the production Groq factory/adapter with the HTTP mock installed inside the child process.

Coverage includes request/model/generation settings, TLS verification, strict schema and compact schema fidelity, response/usage parsing, missing/malformed/refused/incomplete content, model mismatch and tool rejection, HTTP authentication/quota/server/request/redirect failures, timeout/connection sanitization, deadline exhaustion, size bounds, missing key, secret reflection and log/traceback exclusion, credential rotation, fingerprint changes for provider/model/context/output/timeout/temperature, approval enforcement and staleness, and an unchanged Ollama factory. Existing Ollama transport fixtures remain in the regression suite.

One engine fixture succeeds through the existing independent verifier and saves the numeric usage event. Another deliberately fabricates a source ID and persists a failed independent verification. A missing-key engine fixture preserves an empty response and a genuine failed execution/verification. These results test software behavior using fixtures. They supply no evidence of hosted model analytical quality.

Targeted final Groq run passed **24 tests, zero failures/skips, 5.341 seconds**. An initial expanded regression run passed **160 tests, zero failures/skips, 107.831 seconds**. The final full regression result is recorded below after the last Retry-After and fingerprint-test changes.

**Final full regression suite passed 160 tests, zero failures and zero skips, in 107.896 seconds**, using `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`. This retains all 136 existing tests and adds 24 Groq tests. The final log is `data/m10-stage5-1/full-tests-final.txt`. Existing local HTTP fixtures remain part of the full suite; every new Groq HTTP request was mocked. No external inference or installed model is required by these tests.

## Security and preservation review

Before implementation, SHA-256 digests were captured for 19 pre-existing SQLite3 databases and managed JSON artifacts. All hashes matched during review. This includes the old isolated validation database and original research evidence. The failed execution, consumed approval, twelve original selected passages and uncertain inference claim have no mutations. No live approval was created. Fixture approvals exist exclusively in temporary test databases.

`.gitignore` continues to exclude runtime data, databases, logs, virtual environments and `.env` files. No account was created and no real credential was requested or stored. Test credential values are explicitly synthetic. Raw test logs and the protected-file digest inventory are under ignored `data/m10-stage5-1/`. Source/schema/verifier diff checks passed. This review includes the new source and tests even while untracked.

## Next separately authorized live validation

First review this implementation and test report. Then confirm an account's free access to one reviewed strict-schema model, and configure its key outside source control. Select bounded public research evidence and inspect the actual outgoing schema/settings. Resolve the old uncertain inference state through a separately approved recovery procedure before using its database; retain the consumed approval and failure history. Create a fresh operation and approval bound to the hosted destination, selected evidence and generation parameters.

Only after explicit authorization, make one bounded hosted request and retain raw output, usage, latency, independent verification and human factual review. Provider rejection, quota exhaustion or timeout must remain a reported failure. Actual account entitlement, full-schema acceptance, tokenizer fit, provider completion behavior and analytical quality remain unverified.

No commit or push was created during Stage 5.1. Implementation and report await review.
