# M10 Stage 3.3 — Context optimization and synthesis preparation

Date: 2026-10-31, Asia/Calcutta. **Offline preparation completed. No inference, research execution, synthesis execution, approval creation or approval consumption.** No production code, tests, schema, Windows settings, model installation or previous evidence packets were changed.

## 1. Preserved GitHub checkpoint

Repository: https://github.com/JEFFIN-alt/orion; branch `main`.

Local HEAD and GitHub `refs/heads/main` both resolve to **`5c4c2f4741f12edca6e2f3b8f575f17e7ea8eaa2`**, `M10 Stage 3.2: preserve exact research passages and verify projections`. Remote symbolic HEAD points to `main`. Verified with `git ls-remote origin refs/heads/main` and `git ls-remote --symref origin HEAD`.

The five latest commits inspected were `5c4c2f4`, `9f22c6d`, `f95df8e`, `9099881`, and `a460838`. Stage 3.1 remains preserved at `9f22c6d6856902ca69508067f87c71cb3e2ac6a2`, including `reports/M10_STAGE3_RETRY_REPORT.md`. The Stage 3.2 commit contains its report, `passages.py`, synthesis/CLI/verification changes, README and fifteen new deterministic tests. Both reports are tracked. The committed Stage 3.2 report's exact JSON appendix matches the saved baseline preview.

Reviewed the Stage 3.2 change set, source and tests, and report/provenance content. `git diff --check 9f22c6d 5c4c2f4` and `git diff --cached --check` passed. There were no staged or unstaged changes at the start. No new checkpoint commit or push was necessary; no history was rewritten.

`.gitignore` excludes `data/`, `logs/`, `.venv/`, `.env`, `.env.*`, SQLite/database files, logs and Python build/cache outputs. No tracked runtime database, log, virtual environment or environment file was found. A tracked-text scan for private-key headers, GitHub tokens, OpenAI-style keys and AWS access keys found no matches. The reviewed changes contain source code, tests and public-research documentation, with no secret/private runtime content identified; this is a scoped review, not a universal secret-detection guarantee.

This Stage 3.3 report is a new local deliverable, left uncommitted. Generated previews, audit records, sizing fixture and test log are under ignored `data/m10-stage3-3/`. Stage 3.2 remains safely published; there are no source changes to publish for Stage 3.3.

## 2. Provider and budget implementation

Inspected `provider.py`, `ollama.py`, `synthesis.py`, `passages.py`, `synthesis_schema.py`, `synthesis_verify.py`, CLI handling and passage tests. The provider reads process environment using `AIConfig.load()`. The existing Ollama adapter maps `context` to `num_ctx` and `max_output` to `num_predict`, passes the JSON schema as `format`, sets `think=false`, `stream=false`, `keep_alive=0`, and temperature 0.2. No adapter request, including availability, was made here. The specified Ollama 0.40.13 version was not revalidated by an API call.

The passage-mode budget is:

```text
prompt_bytes = UTF8_bytes(canonical({messages: messages, schema: schema}))
effective_byte_limit = min(max_prompt_bytes, context * 2,
                           3 * (context - max_output - 256))
estimated_input_tokens = ceil(prompt_bytes / 3)
estimated_remaining = context - estimated_input_tokens - max_output - 256
```

Canonical serialization uses sorted keys, compact separators and ASCII JSON escaping. Schema size is included in the prompt estimate. This is **three serialized bytes per token**, not Qwen tokenizer output. The actual chat template, JSON/Markdown punctuation, long numeric IDs, Unicode escaping and grammar implementation may differ. HTTP transport bytes are not model tokens. No offline tokenizer is supplied by the current provider interface.

## 3. Measured current versus alternative preview

Generated the alternative through the actual read-only `python -m orion ... synthesis preview` CLI with environment overrides passed only to that subprocess. The model, endpoint, context, timeout, configuration and all selections remain unchanged except maximum output 2048 → 1536. No permanent environment variables were changed.

| Measurement | Current | Alternative |
| --- | ---: | ---: |
| Context tokens | 4096 | 4096 |
| Maximum output tokens | 2048 | 1536 |
| Estimated input tokens | 1774 | 1774 |
| Framing allowance | 256 | 256 |
| Estimated total | 4078 | 3566 |
| Estimated remaining context | 18 | **530** |
| Canonical prompt bytes, including schema | 5322 | 5322 |
| Canonical schema bytes | 1944 | 1944 |
| Canonical messages bytes | 3355 | 3355 |
| Effective prompt byte limit | 5376 | 6912 |
| Remaining permitted prompt bytes | 54 | 1590 |
| Worker execution timeout | 60 s | 60 s |
| Provider timeout | 60 s | 60 s |

Exact calculations: `5322 / 3 = 1774`; `1774 + 2048 + 256 = 4078`; `4096 - 4078 = 18`. Alternative: `1774 + 1536 + 256 = 3566`; `4096 - 3566 = 530`. Effective alternative byte limit: `min(12000, 8192, 3 * 2304) = 6912`.

The alternative exceeds the requested 300-token estimated margin by 230 tokens. If framing really costs 256 tokens, actual input could reach 2304 tokens before exhausting context, but must stay at or below 2004 to retain a 300-token margin. Thus the desired margin tolerates only about 13% input-estimation error; 530 is not guaranteed real headroom. The evidence and messages were not shortened to obtain this result.

## 4. Is 1536 output tokens sufficient?

**A reasonable candidate for a concise complete report, not proven adequate for this model.** The full contract requires 13 top-level fields, but does not require eight entries in each array or maximum-length prose. A short executive summary, four brief findings, one comparison, one advantage/disadvantage, explicit limitations, one unresolved question, a withheld recommendation, two next investigations and a short confidence explanation can retain every field.

For a concrete offline capacity check, a **hand-authored sizing fixture, not provider output or a research synthesis execution**, was passed through the existing local analysis validator and citation resolver. It contains all 13 fields and the counts above. Its compact JSON is 2277 bytes, corresponding to 759 tokens only under the same rough three-bytes estimate. It uses actual selected source IDs and a visibly placeholder execution UUID, and remains in ignored local data. It establishes that a concise valid structure is possible; it does not establish model quality, factual support or Qwen token count.

1536 tokens will not accommodate every allowed list at eight entries and 1200 characters per text field. The unchanged model prompt does not guarantee concision. Long prose, citation overhead, schema-constrained generation overhead or slow decoding may exhaust the output/deadline. No schema fields, maxima, citation requirements or verification checks were removed. A truncated/incomplete JSON response must remain a failed result, with no automatic retry or fabricated completion. No inference was used to obtain a favorable sizing result.

## 5. Verified evidence binding

Research execution: `1614e92f-45f7-4161-8672-73de5cfd3f93`.

Original packet SHA-256: `fca20fd13cf7c2f0ab4a3036c5d85c0ea8ed0bd956eb85355ac1973ffe923827`.

Projection SHA-256: `b5611efc24627e9afb6f73bc9a1392515c728b6d7985ed6f67c78b889643e7b8`.

Latest required research verification: `7d490c72-062a-4cf9-88eb-882e33e6f68b`, passed. The two existing research verification records remain unchanged. The existing `select_evidence` service rechecked successful execution, current dependency eligibility, configuration/capture digests and managed packet provenance. `validate_projection` independently re-extracted the selected slices from that packet. No new persisted verification record was created for this preview.

The artifact was resolved from the existing research records under `data/m10-stage3-retry/artifacts/`, not from a user/model-selected source path. Source URLs, original evidence digests, exact Unicode slices, offsets and every passage SHA-256 match the originals. All 12 slices / 1753 Unicode characters are unchanged. The alternative messages and schema compare equal to the prior preview. The projection digest is unchanged because output budget is model configuration, not evidence content; any later approval must nevertheless bind the new model configuration through the complete operation fingerprint.

| Repository | Original source ID | Original URL | Relevant selected evidence |
| --- | --- | --- | --- |
| Verba | repository:672002598 | https://github.com/weaviate/Verba | Hybrid search; token/sentence chunking; embedded Weaviate Windows limitation |
| R2R | repository:756142546 | https://github.com/SciPhi-AI/R2R | RESTful retrieval architecture; reciprocal rank fusion |
| GraphRAG | repository:778431525 | https://github.com/microsoft/graphrag | LLM structured extraction; indexing cost warning |
| LightRAG | repository:866513204 | https://github.com/HKUDS/LightRAG | Graph/vector architecture; hybrid and naive modes; RAGAS/context precision; comparative row with headings |

Offsets below are original zero-based Unicode code points, start inclusive and end exclusive, in `readme`. SHA-256 covers the exact selected text encoded as UTF-8, with no normalization.

| Source ID | Start | End | Passage SHA-256 |
| --- | ---: | ---: | --- |
| repository:672002598 | 7728 | 7848 | `1385ea3dd4bb5b891a156e9a06ab8778a900eb2af1f941d71e9d0b5c982ee5b0` |
| repository:672002598 | 9140 | 9336 | `302931e78c079d022794af8e222c9ff677842e0f2888fed212692282ee8e63b5` |
| repository:672002598 | 30850 | 30910 | `b4cc4038e3ffa0a46e3f7ff5f8a71b4b9854996b1dd62ca4f57e7efc7538978a` |
| repository:756142546 | 1648 | 1788 | `31e349e7f18bab6fe2c8726c8132a2cf611b1f8f4a5bc03e3729cd905d67f513` |
| repository:756142546 | 3804 | 3880 | `f2e3e2c28411050e288b3028109c30f10ab2994460330bc4ba0c1bfbc272dc12` |
| repository:778431525 | 1425 | 1593 | `8eb728c6729f8e78f39ea45f246f646b8dc854f1b1e2111b276123df81c88be3` |
| repository:778431525 | 2315 | 2463 | `8dfda5b5423d0753d96f34eb561d8d8507bd14960294d7ceb492d9f48eab65d5` |
| repository:866513204 | 5116 | 5288 | `67fa59c22daa4e84a89ca0d5cb6389ddb21d763063d77cff0095cea74f3e650c` |
| repository:866513204 | 15577 | 15771 | `496db61c84d6cc303deb8a4297b604498a1c31d50e44d33237d516a3d9b37589` |
| repository:866513204 | 22832 | 22906 | `2bcd92d289028b8b780dc01dddebcf71905506c78db2a02a2d3a58bbd2d1b9c2` |
| repository:866513204 | 23038 | 23098 | `74b99ff279e583cfcff37fc740fa9885f922c62c378b7eab1408c800728df624` |
| repository:866513204 | 39255 | 39600 | `df86e2a6d24f79bb1f3467cacf31c5ed7578865c26cd591c8f66f0137d6248e2` |

Six source records are explicitly omitted: `doi:10.5040/9781350865778`, `doi:10.1002/9781394374717.ch03`, `doi:10.1002/9781394374717.ch07`, `doi:10.5040/bci-0kgd.ch-1`, `doi:10.59350/q2pq3-0fv85`, `repository:753591102`.

Original metadata is explicitly omitted in passage mode. The full projection retains source IDs/URLs, original evidence digests, provider outcomes, limitations, omitted-source IDs and per-field omitted ranges/nontext markers. The compact model transport supplies exact passages, IDs, URLs and omitted-source count, not full omitted metadata or entire documents. Those omissions were checked by reconstructing the full projection, not merely comparing its claimed digest. The comparative table includes headings and a single source-reported row; missing methods and rows prevent defensible ranking. Selection bias, author claims and incomplete evidence remain limitations. Retrieved text is untrusted data, with no tool or code-execution authority.

## 6. Offline schema compatibility and tests

Expanded every local `$ref` in the compact `$defs` schema and compared it with the complete original analysis schema scoped to the same four source IDs: exact equality. Packet-specific reference enums remain intact; the global schema was not mutated. Required fields remain:

`schema_version`, `execution_id`, `question`, `executive_summary`, `key_findings`, `comparisons`, `advantages`, `disadvantages`, `evidence_limitations`, `unresolved_questions`, `recommendation`, `next_experiments`, `confidence`.

Exact allowed fields, string bounds, at-most-eight claim entries, at-most-ten unique references, valid confidence levels, and existing local citation policy remain unchanged. The compact schema itself is byte-for-byte equivalent between saved previews. This does **not** establish that Ollama accepts the `$defs`/`$ref` grammar or that Qwen will produce a valid, grounded answer.

Ran the 11 pure `test_passages.PassageTests` contract tests: **11 passed, 0 failed, 0 skipped**, 0.006 seconds. These cover offsets/hashes, invalid ranges, omissions, tampering, budget enforcement, compact schema equivalence and untrusted text separation. No worker or model execution is included in this subset.

Latest full regression suite remains **136 passed, 0 failed, 0 skipped**, 175.326 seconds, from Stage 3.2; confirmed its recorded log and unchanged committed source/tests. The full suite was not rerun here because no implementation changed and this stage forbids synthesis execution; broader fixture execution tests were already run in Stage 3.2. Neither these tests nor the sizing fixture establish real-model analytical quality.

## 7. Read-only audit and local artifacts

Before/after complete table snapshots of the isolated validation database were identical. It still contains one research execution, one original collection approval, two research verifications, zero synthesis configurations/runs and zero inference claims. All pre-existing SQLite3 databases and JSON files in managed artifact directories found under `data/` retained their SHA-256 bytes. The original weak Stage 3 packet and Stage 3.1 focused packet are unchanged. No previous approval was consumed, and no new task, execution, verification or approval was created.

Local ignored audit files:

- `data/m10-stage3-3/preview-1536.json`: complete alternative operation, messages and schema.
- `data/m10-stage3-3/audit.json`: measured budgets, complete passage inventory, binding, database counts and before/after hashes.
- `data/m10-stage3-3/offline-contract-tests.txt`: actual 11-test result.
- `data/m10-stage3-3/hand-authored-sizing-fixture.json` and `capacity.json`: explicitly non-AI capacity example and measurement.
- `data/m10-stage3-3/memory.json`: resource snapshot.
- `prepare.py`, `capacity.py`, `write_report.py` in that directory: local audit/report helpers, not new production interfaces.

Alternative preview file SHA-256: `c374dd4d2ba3402927e0e3c725189050affce425f611ccb90fd9730421b492fa`. This file digest differs from the canonical evidence projection digest and is not an approval fingerprint.

## 8. Memory and remaining runtime risks

Snapshot at **2026-10-31T11:42:03.2172400+05:30**: Windows reports **709.5 MiB free RAM** out of **7832.5 MiB visible RAM**. GPU query: `NVIDIA GeForce RTX 2050, 4096 MiB, 327 MiB, 3636 MiB` (name, total, used, free VRAM). Earlier in this preparation session free RAM was approximately 751 MiB, then 732 MiB. No applications were closed or Windows settings changed.

This is low host-memory headroom for loading a model alongside Windows. Free GPU memory does not replace host RAM, and model weights, runtime allocations, context/KV cache and staging buffers require additional memory. Exact additional RAM/VRAM requirements were **not measured** because loading/inference is forbidden here. Reducing output reservation improves the estimated context balance; it does not reduce the fixed 4096 context setting or guarantee lower allocated memory. Paging, timeout and instability remain risks. Recheck RAM/VRAM immediately before and after any future authorized call, and defer if critical pressure or instability is present. The current preparation is not a declaration that live execution is safe now.

## 9. Recommended next experiment and exact command recipe

Proposed worker: `research-synthesize`; provider `ollama`; model `qwen3.5:2b-q4_K_M`; loopback endpoint `http://127.0.0.1:11434`; context **4096**; output **1536**; provider/worker timeout **60 seconds**; 12 unchanged passages; max sources 10; excerpt bound 800 characters; prompt bound 12000 bytes (effective 6912); response bound 16000 bytes. One attempt only, no automatic retry, generated-code execution or downstream task. Preserve standard dependency checks, task approval and independent verification.

The following commands are a **future recipe only, not run in Stage 3.3**. A task ID and approval ID do not exist yet and must come from Orion, not fabricated constants. Use the existing isolated Stage 3.1 validation database containing the verified provenance. Do not point these commands at production. Apply these environment values in a temporary PowerShell session and close that session afterwards; do not use `setx` or persistent Windows environment changes.

```powershell
Set-Location 'C:\Users\JEFFIN\Projects\orion'
$env:ORION_AI_PROVIDER = 'ollama'
$env:ORION_AI_ENDPOINT = 'http://127.0.0.1:11434'
$env:ORION_AI_MODEL = 'qwen3.5:2b-q4_K_M'
$env:ORION_AI_CONTEXT = '4096'
$env:ORION_AI_MAX_OUTPUT = '1536'
$env:ORION_AI_TIMEOUT = '60'
$orionPython = '.\.venv\Scripts\python.exe'
$orionDb = 'C:\Users\JEFFIN\Projects\orion\data\m10-stage3-retry\validation.sqlite3'
$orionLogs = 'C:\Users\JEFFIN\Projects\orion\data\m10-stage3-3\live-logs'
```

After a later instruction authorizes preparing a real proposal, create a new approval-required task in project `57b1cb0c-8f39-4c63-acf3-91eb10cb9662`, using `tasks create ... --project ... --require-approval`. Set `$orionSynthesisTask` to its actual returned ID. Configure the exact saved selections via the existing CLI; the Python wrapper below avoids Windows JSON quoting ambiguity and never treats a file as research evidence (only the selection array is loaded):

```powershell
@'
import json, sys
from pathlib import Path
from orion.cli import main
p = json.loads(Path('data/m10-stage3-3/preview-1536.json').read_text(encoding='utf-8'))
cfg = p['operation']['configuration']
argv = ['--database', sys.argv[2], '--log-dir', sys.argv[3],
        'synthesis', 'configure', sys.argv[1],
        '--source-execution', '1614e92f-45f7-4161-8672-73de5cfd3f93',
        '--passages', json.dumps(cfg['passages'])]
for key, value in cfg.items():
    if key != 'passages': argv.extend(['--'+key.replace('_','-'), str(value)])
raise SystemExit(main(argv))
'@ | & $orionPython - $orionSynthesisTask $orionDb $orionLogs

& $orionPython -m orion --database $orionDb --log-dir $orionLogs synthesis show $orionSynthesisTask
& $orionPython -m orion --database $orionDb --log-dir $orionLogs approvals request $orionSynthesisTask research-synthesize --reason 'One bounded Qwen synthesis; 12 verified passages; 4096 context, 1536 output, 60 seconds; no retries'
```

**STOP at the returned approval request.** Inspect its actual ID, fingerprint, source execution/digests, dependency eligibility and exact model/configuration. Present that concrete proposal plus fresh memory readings to the CEO. Neither this report nor an earlier collection/Stage 2 approval authorizes it. A fresh explicit CEO decision is required before recording approval or issuing execute. Any material evidence, selection or configuration change requires a fresh proposal/decision.

Only after that exact CEO approval, set `$orionApprovalId` to the returned request ID, record the actual decision with Orion's `approvals decide`, and run precisely one execution:

```powershell
# ONLY AFTER the CEO explicitly approves this actual request/fingerprint:
& $orionPython -m orion --database $orionDb --log-dir $orionLogs approvals decide $orionApprovalId approved --reason 'CEO explicitly approved this exact proposal and its one-attempt limits'
& $orionPython -m orion --database $orionDb --log-dir $orionLogs execute $orionSynthesisTask research-synthesize
```

Inspect the actual returned execution ID with `execution`, `synthesis summary`, `synthesis packet` and `verifications`; do not rerun to force success. The engine's independent verification remains authoritative for structure/provenance, with human review needed for factual support. A timeout or provider/schema failure is a real failure, not permission to reset/retry automatically. No task/approval was created and none of these mutating future commands was run during this stage.

## 10. Stop condition

Preparation is complete. The alternative passes offline budget, schema and provenance checks with a **530-token estimated margin**, preserves all 12 exact passages and all required fields, and is the recommended configuration for one later explicitly approved experiment **subject to a fresh resource check**. Actual tokenizer fit, Ollama compact-schema acceptance, response completion within 1536 tokens/60 seconds, memory safety and analytical quality remain unverified. Stop here; no live test is authorized by this preparation.
