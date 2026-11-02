# M10 Stage 5.1.1 — Groq adapter source review and correction

Review date 2026-10-31, Asia/Calcutta. Repository `C:\Users\JEFFIN\Projects\orion`, branch `main`, HEAD `917705854831fe248eca0a7234855592a46b131d`.

**Verdict — the confirmed adapter defects described below are corrected and covered by offline regressions. Proceed to CEO review of a separately authorized live-validation plan. Full server-schema compatibility, account permissions and free quotas remain unverified. The old uncertain inference slot remains a blocker to executing in its database.**

## Actual source and working-tree review

Reviewed the complete Stage 5.1 tracked diff for `provider.py`, `ollama.py`, `synthesis_worker.py` and `execution.py`, plus the untracked `groq.py`, `test_groq.py` and Stage 5.1 report. The pre-existing Stage 3.4 report was also inspected as a historical approval-preparation snapshot. Its pending-request wording predates the failed execution; the actual database now records a consumed approval and is authoritative for current state.

Reviewed the configuration serialization, synthesis prompt/schema creation, approval proposal hashing/authorization, execution claim and artifact flow, independent verifier, conversation response persistence and logging. Existing Ollama, synthesis and passage test conventions were inspected. No staged changes were present.

This review changes only `src/orion/groq.py`, `tests/test_groq.py` and this new report relative to the Stage 5.1 working tree. The existing worker, provider interface, independent verifier and output schema were retained. No dependency was added.

## Official model-list discrepancy

The official documentation version retrieved during this review explicitly lists **four** strict-mode models under “Models with Strict Mode (`strict: true`)”:

1. `openai/gpt-oss-20b`
2. `openai/gpt-oss-120b`
3. `qwen/qwen3.8-27b`
4. `meta-models/muse-spark-open`

The fourth entry appears in the supported-model table, adjacent to the three requested names. Therefore the claimed absence of Muse Spark Open could not be confirmed from the retrieved official page. Its allowlist entry was retained. A regression now explicitly exercises strict payload construction for each of the three requested models. Another rejects the documented best-effort-only `openai/gpt-oss-safeguard-20b` before HTTPS transport creation. Existing tests reject arbitrary unsupported model identifiers. [Groq supported models](https://console.groq.com/docs/structured-outputs#supported-models)

Retrieval limits matter here. The web source was marked crawled today and returned the four-entry table. A direct unauthenticated Python fetch of the documentation returned HTTP 403, and an additional query-string fetch through the web tool was inaccessible. These failures supplied no contradictory model table. No authenticated model endpoint or account entitlement check was performed. If the CEO sees a newer three-entry official table, reconcile that specific version before selecting a model. This report documents the version actually retrieved rather than claiming that all accounts expose all four models.

## Confirmed defects and minimal fixes

### 1. JSON-escaped credential reflection could pass the redaction guard

The original guard searched the raw HTTP bytes for the environment credential. A mocked response with every credential character written as a Unicode JSON escape passed that check. Parsing returned the literal synthetic key as `Response.content`; this was reproduced before correction. Such content could then reach normal conversation or synthesis persistence.

Added a credential check on decoded content. Synthesis content can itself be JSON, so the guard also checks one decoded content-JSON layer to cover an escaped credential inside an otherwise valid analysis object. A static `credential_exposure` error replaces the content. Ordinary malformed model JSON still proceeds to the existing independent validation path unless it exposes the credential. Added a regression covering both escape layers. Raw-byte detection remains in place. No real key was used.

### 2. An expired final read could be accepted as a completed response

A mock advanced the monotonic clock beyond the configured deadline while returning the final empty body chunk. The previous implementation broke out of the loop and returned a successful response despite elapsed time exceeding the timeout. This was reproduced before correction. Delayed headers could likewise bypass the next loop check when the status was an immediate error.

Added deadline checks immediately after receiving headers and after every body read, including EOF. Expired responses now raise the existing sanitized `timeout` error with uncertainty retained. Added a regression covering late headers and EOF, including a closed connection socket. The connection is still closed in `finally`; request count remains one.

Socket timeouts and elapsed-time checks detect or bound normal transport waits. They do not turn Python DNS resolution and every OS call into a separately cancellable wall-clock timer. Synthesis retains the existing spawned-worker execution deadline as its outer bound. No timeout retry or additional provider request was introduced.

### 3. Oversized integer usage could escape malformed-response handling

The original usage check called `math.isfinite` before applying the numeric maximum. A valid JSON integer such as `10**400` overflows conversion inside `math.isfinite`, raising `OverflowError` instead of the intended malformed-response error. Reordered the existing conditions to reject negative or greater-than-`10**12` values first. Added this value to the malformed-response regression cases.

## Security and transport review

| Area | Source finding and validation |
|---|---|
| Credential isolation | Key is read at request time from `ORION_GROQ_API_KEY`, stored in the Authorization header, and absent from the configuration dataclass. Credential-rotation tests confirm equal approval fingerprints and absence of synthetic keys in test databases |
| Redaction | Fixed provider errors discard untrusted HTTP bodies and suppress underlying exception text. Raw and decoded credential reflection guards now cover the confirmed bypass. Existing traceback/log tests remain in the targeted suite |
| Destination | Exact configured endpoint must equal `https://api.groq.com/openai/v1/chat/completions`. Transport fixes host, port and path. Alternate HTTP URLs, query strings, trailing paths and unrelated hosts are rejected |
| TLS | Uses `ssl.create_default_context`; tests assert certificate verification and hostname checking remain enabled |
| Redirects | 3xx produces a categorized HTTP error. No redirect implementation or follow-up request exists |
| HTTP failures | Authentication, quota/rate limit, request/schema/model rejection and server errors have distinct safe codes/statuses. Retry-After is normalized to a wait value, with no automatic retry |
| Deadlines | Shared monotonic request deadline is reapplied between phases and checked after headers and reads. Timeout/connection errors preserve uncertainty. The engine retains its separate worker limit |
| Bounds | Request at most 64 KiB, full response at most 128 KiB, generated content at most 16,000 UTF-8 bytes. Existing synthesis prompt limits and response limits still apply |
| Model output | Requires one completed assistant choice, expected model identity, content, and no tool/function call. Refusal, incomplete output, invalid role, malformed JSON or invalid numeric metrics produce real errors |
| Approval binding | Existing proposal hashing includes provider, endpoint, model, context budget, maximum output, timeout and temperature. Parameter changes invalidate the operation fingerprint; credential rotation does not |
| Usage persistence | Whitelisted finite numeric token counts and timing values are carried through the response and saved as a `synthesis_provider_usage` event. Saved synthesis metadata keeps the original exact field set |
| Ollama | Loopback checks, factory path and default temperature remain intact. No local model was loaded during this review |
| Retry/fallback | One HTTP request per adapter call. No automatic provider substitution or schema-mode downgrade was found |

The static model-capability set and mandatory strict-mode policy are code behavior rather than newly configurable generation settings. Free availability is never inferred from allowlist membership. Orion's `context` value remains its application budgeting parameter; Groq receives maximum completion tokens and does not receive Ollama's context-allocation setting.

## Exact schema comparison

| Feature | Present in Orion synthesis | Official Groq documentation retrieved | Review conclusion |
|---|---|---|---|
| `$defs` / `$ref` | Compact passage-mode schema | Explicit reusable-definition example | Documented mechanism; exact request acceptance remains a live question |
| `enum` | Schema version, confidence level and packet-specific source IDs | Explicitly supported and demonstrated | Preserved |
| Nested objects and arrays | Claims, recommendations, lists and confidence | Supported and demonstrated | All Orion objects are closed and all properties required |
| `anyOf` | Absent from this exact synthesis contract | Explicitly documented composition | No synthesis conversion needed |
| `minLength` | Required text and identifiers | No keyword mention found on retrieved page | Provider enforcement unverified; local bounds retained |
| `maxLength` | Text and identifier bounds | No keyword mention found | Provider enforcement unverified; local bounds retained |
| `maxItems` | Claim and reference limits | No keyword mention found | Provider enforcement unverified; local bounds retained |
| `uniqueItems` | Source references | No keyword mention found | Provider enforcement unverified; duplicate-reference rejection retained locally |

Every schema call transmits the existing schema without removing keywords or changing strict mode. Structural preflight checks only the documented closed-object/required-field conditions; it does not certify every possible schema against the remote compiler. Existing compact-schema tests check bounds, references and packet-specific enums. The synthesis verifier remains the authority for local structure/provenance, with factual support requiring human review. Server rejection must stop validation and preserve the actual error; an HTTP success must still pass local checks. [Groq schema requirements](https://console.groq.com/docs/structured-outputs#schema-requirements)

## Tests

Stage 5.1's recorded full baseline was 160 passing tests. Added four test methods, plus subcases in existing tests, for the two escaped-content layers, late-header/EOF timeout rejection, accepted three-model strict payloads and best-effort-only pretransport rejection. The oversized integer is an additional malformed-response subcase.

Targeted command `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_groq.py -v` passed **28 tests, zero failures or skips, in 5.488 seconds**. All Groq HTTP transport is mocked. Isolated fixture tests retain successful independent verification, fabricated-source rejection, key exclusion, usage-event persistence, missing-key failure and approval fingerprint/staleness coverage.

Full regression command `.\.venv\Scripts\python.exe -m unittest discover -s tests -q` passed **164 tests, zero failures and zero skips, in 107.433 seconds**. This retains the 160-test Stage 5.1 suite and adds four test methods. Existing Ollama HTTP fixtures and independent verifier tests passed as part of this run.

Logs are under ignored `data/m10-stage5-1-1/`. The existing full suite includes local loopback HTTP fixtures. No Groq API endpoint was contacted and no hosted model output was generated.

## Preservation and Git

Before corrections, the 19 protected Stage 5.1 database/artifact hashes still matched. The review added hashes for the saved 1536-output preview, configured twelve-passage operation and independent schema/verifier/passage source files, making 24 protected paths. The original packet hash remains `fca20fd13cf7c2f0ab4a3036c5d85c0ea8ed0bd956eb85355ac1973ffe923827`; the saved projection digest remains `b5611efc24627e9afb6f73bc9a1392515c728b6d7985ed6f67c78b889643e7b8`, with twelve selections.

After the full suite, all 24 hashes matched again. Independently re-extracting the twelve slices through `validate_projection` reproduced the saved projection. Modified and untracked files passed whitespace and scoped credential-pattern review. The index remained empty and HEAD retained its original hash.

Read-only SQLite inspection reconfirmed execution `21a04b45-f0bd-4cac-a91f-1e2a76ff9977` is failed at attempt 1. Approval `4e502cb1-c761-4f57-8072-c2e2de5ee549` remains approved and consumed by that execution, with original fingerprint `8d30a3bea288d65f4664e5a205e1bd568ed9addb9134a06447dd47db467821bf`. The independent verification remains failed. The inference claim still references that execution with `uncertain=1`.

At entry the tracked working changes were `execution.py`, `ollama.py`, `provider.py`, and `synthesis_worker.py`, all from Stage 5.1. Untracked files were `groq.py`, `test_groq.py`, the Stage 5.1 report and the earlier Stage 3.4 report. This stage adds this untracked review report and corrects the untracked adapter/test files. No file was staged, committed or pushed. No source changes were made to approvals, verifier, schema, evidence selection or collection. No recovery mutation or live approval occurred. No account or credential was requested.

## Readiness and CEO stop boundary

The corrected implementation is a candidate for a bounded, separately authorized live compatibility test using a documented model with account-confirmed access. That test must establish full-schema acceptance, actual token usage, returned model identity, raw response behavior and analytical quality. The old validation database cannot execute while its uncertainty gate remains. Resolve that state only through separately authorized recovery, retain the failed history and consumed approval, then prepare a fresh approval bound to the actual hosted destination and configuration.

Review ends here, awaiting CEO review. This stage authorizes no account setup, recovery or live inference.
