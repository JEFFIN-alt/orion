# M10 Stage 3.4 — Evidence-rich synthesis approval preparation

Date: 2026-10-31 (Asia/Calcutta). **Prepared only. Request is pending; no approval decision, inference or synthesis execution occurred.**

## GitHub checkpoint

Reviewed `reports/M10_STAGE3_3_CONTEXT_OPTIMIZATION_REPORT.md` for secrets and private runtime content. Its content is the intended engineering report: public-source references, provenance identifiers, budget calculations, hardware readings and operator commands. No credentials, database contents, private conversation data or generated runtime artifacts were included. Local paths identify the already specified repository, not credentials. Only this report was staged; staged whitespace validation passed.

Committed and pushed to https://github.com/JEFFIN-alt/orion on `main`:

**`af8580c3114412c60702191bc5a47520810b34f3` — M10 Stage 3.3: context optimization and synthesis preparation**.

Remote `refs/heads/main` was independently checked with `git ls-remote` and matches local HEAD. No force-push or history rewrite. Working tree was clean immediately after that push. This new Stage 3.4 report is left local/uncommitted; runtime preparation files and the validation database remain ignored under `data/`.

## Actual task and pending approval

| Field | Recorded value |
| --- | --- |
| Isolated database | `data/m10-stage3-retry/validation.sqlite3` |
| Project | `57b1cb0c-8f39-4c63-acf3-91eb10cb9662` |
| Task | `de4cca0b-ba2f-43ba-8281-93a0d508c300` |
| Task title | M10 Stage 3.4: first evidence-rich Qwen synthesis |
| Task status | pending; approval required |
| Worker | research-synthesize, version 1 |
| Configured operation | `ddc6bb07-05f7-4577-a3be-50a8909c5f7a` |
| Approval request | **`4e502cb1-c761-4f57-8072-c2e2de5ee549`** |
| Approval status | **pending** |
| Created at (UTC) | `2026-10-31T06:18:54.150379+00:00` |
| Decision / execution | `decided_at=null`; `execution_id=null` |

Approval fingerprint:

`8d30a3bea288d65f4664e5a205e1bd568ed9addb9134a06447dd47db467821bf`

Exact recorded reason:

> One bounded Qwen synthesis using 12 verified original research passages, context 4096, output 1536, 60-second timeout, one attempt only, no retries or downstream execution.

The new task was created with `Service.create_task(..., require_approval=True)`, configured through `SynthesisService.configure`, and submitted through the existing `ApprovalService.request`. No replacement approval framework, custom SQL approval decision or execution path was introduced. One approval is single-use under the existing engine. One attempt, no retries and no downstream execution are the authorized experiment limits, also recorded in the task description and request reason; no scheduler was started.

Before requesting approval, inspected the actual complete proposal and recomputed its fingerprint. It binds task ID, worker metadata/version, 60-second worker timeout, isolated data directory, project and task snapshot, dependency edges, synthesis operation ID/configuration/time, upstream execution/task/project, latest verification ID, packet digest, full evidence projection, exact selections, projection digest and complete model metadata. After request creation, retrieved the stored request and compared its canonical proposal and fingerprint with a freshly recomputed proposal in another process. They match.

An initial local audit-helper comparison stopped before creating any request because Python worker capabilities are a tuple while saved JSON restores them as a list. Diagnostic checks showed identical canonical JSON and identical fingerprints, with no provenance/configuration change and zero requests for the task. The helper was corrected to compare canonical JSON, matching Orion's existing fingerprint format. Production code and verification rules were unchanged. Exactly one pending request was subsequently created.

## Source evidence and verification

| Binding | Verified actual value |
| --- | --- |
| Research execution | `1614e92f-45f7-4161-8672-73de5cfd3f93` |
| Research task | `13658fc7-4bf3-4a8d-a5d3-2fd275dd2631` |
| Packet SHA-256 | `fca20fd13cf7c2f0ab4a3036c5d85c0ea8ed0bd956eb85355ac1973ffe923827` |
| Projection SHA-256 | `b5611efc24627e9afb6f73bc9a1392515c728b6d7985ed6f67c78b889643e7b8` |
| Latest required verification | `7d490c72-062a-4cf9-88eb-882e33e6f68b` |
| Verification result | `passed` |
| Latest verification timestamp | `2026-10-30T18:43:42.877105+00:00` |

These values were verified against the actual database and managed artifact bytes using `select_evidence`, not trusted from the directive. Database schema version 8, integrity and foreign-key checks passed. The source is a successful research-collect execution with completed dependency evidence. Original recorded configuration/captures and packet digests were checked by existing provenance validation. Both existing research verification records remain unchanged; no new persisted verification was created here.

The saved Stage 3.3 preview was regenerated read-only under the exact temporary model settings and compared for complete equality. `validate_projection` reconstructed all original selections; every source ID, URL, source evidence digest, passage text, character range and UTF-8 passage hash matched. The new configured operation equals that preview operation except for its legitimate newly assigned operation ID and configuration timestamp. No sources, URLs, passages or evidence were changed.

## All twelve passage references

All fields are `readme`. Offsets are zero-based Unicode code points, inclusive start and exclusive end. SHA-256 hashes the exact selected UTF-8 text, without normalization.

| Source ID | Original URL | Start | End | Passage SHA-256 |
| --- | --- | ---: | ---: | --- |
| repository:672002598 | https://github.com/weaviate/Verba | 7728 | 7848 | `1385ea3dd4bb5b891a156e9a06ab8778a900eb2af1f941d71e9d0b5c982ee5b0` |
| repository:672002598 | https://github.com/weaviate/Verba | 9140 | 9336 | `302931e78c079d022794af8e222c9ff677842e0f2888fed212692282ee8e63b5` |
| repository:672002598 | https://github.com/weaviate/Verba | 30850 | 30910 | `b4cc4038e3ffa0a46e3f7ff5f8a71b4b9854996b1dd62ca4f57e7efc7538978a` |
| repository:756142546 | https://github.com/SciPhi-AI/R2R | 1648 | 1788 | `31e349e7f18bab6fe2c8726c8132a2cf611b1f8f4a5bc03e3729cd905d67f513` |
| repository:756142546 | https://github.com/SciPhi-AI/R2R | 3804 | 3880 | `f2e3e2c28411050e288b3028109c30f10ab2994460330bc4ba0c1bfbc272dc12` |
| repository:778431525 | https://github.com/microsoft/graphrag | 1425 | 1593 | `8eb728c6729f8e78f39ea45f246f646b8dc854f1b1e2111b276123df81c88be3` |
| repository:778431525 | https://github.com/microsoft/graphrag | 2315 | 2463 | `8dfda5b5423d0753d96f34eb561d8d8507bd14960294d7ceb492d9f48eab65d5` |
| repository:866513204 | https://github.com/HKUDS/LightRAG | 5116 | 5288 | `67fa59c22daa4e84a89ca0d5cb6389ddb21d763063d77cff0095cea74f3e650c` |
| repository:866513204 | https://github.com/HKUDS/LightRAG | 15577 | 15771 | `496db61c84d6cc303deb8a4297b604498a1c31d50e44d33237d516a3d9b37589` |
| repository:866513204 | https://github.com/HKUDS/LightRAG | 22832 | 22906 | `2bcd92d289028b8b780dc01dddebcf71905506c78db2a02a2d3a58bbd2d1b9c2` |
| repository:866513204 | https://github.com/HKUDS/LightRAG | 23038 | 23098 | `74b99ff279e583cfcff37fc740fa9885f922c62c378b7eab1408c800728df624` |
| repository:866513204 | https://github.com/HKUDS/LightRAG | 39255 | 39600 | `df86e2a6d24f79bb1f3467cacf31c5ed7578865c26cd591c8f66f0137d6248e2` |

The unchanged 1753 selected Unicode characters cover Verba hybrid search/chunking/Windows limitation, R2R architecture/reciprocal rank fusion, GraphRAG architecture/indexing costs, and LightRAG architecture/retrieval modes/evaluation discussion/comparative table headings and row. Six sources and unselected document portions remain explicitly omitted. Source-reported performance claims lack complete methodology; this is not a basis for declaring a winner.

## Model configuration and context budget

Only temporary PowerShell process environment variables were used:

```powershell
$env:ORION_AI_PROVIDER = 'ollama'
$env:ORION_AI_ENDPOINT = 'http://127.0.0.1:11434'
$env:ORION_AI_MODEL = 'qwen3.5:2b-q4_K_M'
$env:ORION_AI_CONTEXT = '4096'
$env:ORION_AI_MAX_OUTPUT = '1536'
$env:ORION_AI_TIMEOUT = '60'
```

The recorded operation matches these values, including provider timeout 60 seconds. Worker execution timeout is also 60 seconds. Other limits remain max sources 10, per-passage excerpt bound 800 characters, max prompt 12000 bytes, max response 16000 bytes. Actual passage count is 12 across four source records.

| Measurement | Value |
| --- | ---: |
| Canonical prompt including schema | 5322 bytes |
| Schema | 1944 bytes |
| Estimated input, ceiling(5322 / 3) | 1774 tokens |
| Reserved output | 1536 tokens |
| Framing allowance | 256 tokens |
| Estimated total | 3566 tokens |
| Context | 4096 tokens |
| Estimated remaining | **530 tokens** |
| Effective prompt byte limit | min(12000, 8192, 3 × (4096 − 1536 − 256)) = 6912 |

The margin exceeds the 300-token target, but the three-serialized-bytes/token calculation is a heuristic, not actual Qwen tokenization. The unchanged compact schema's offline equivalence was established in Stage 3.3. Actual Ollama `$defs`/`$ref` compatibility, completion within 1536 output tokens/60 seconds, and analytical quality remain unverified. Provider process presence does not demonstrate that the service/model is ready. No Ollama HTTP request or model load was made here.

## Fresh resource snapshots

| Reading | Before preparation | After request/fresh-process audit |
| --- | --- | --- |
| Local timestamp | 2026-10-31T11:47:10.7073806+05:30 | 2026-10-31T11:49:01.0852762+05:30 |
| Available RAM | 374.1 MiB (383080 KiB) | **820.7 MiB** (840348 KiB) |
| Total OS-visible RAM | 7832.5 MiB | 7832.5 MiB |
| GPU | NVIDIA GeForce RTX 2050 | NVIDIA GeForce RTX 2050 |
| Total VRAM | 4096 MiB | 4096 MiB |
| Used VRAM | 327 MiB | 329 MiB |
| Available VRAM | 3636 MiB | **3634 MiB** |
| GPU utilisation | 21% | **16%** |

RAM readings are from `Win32_OperatingSystem`; GPU readings are from `nvidia-smi`. GPU total/used/free may not sum exactly because of reserved memory. Ollama processes were running at both snapshots:

| Process | PID | Initial working set | Final working set |
| --- | ---: | ---: | ---: |
| ollama | 9796 | 50.48 MiB | 50.43 MiB |
| ollama app | 9120 | 41.14 MiB | 44.14 MiB |

**Resource warning:** available RAM remains below 1 GiB and fluctuated from about 374 to 821 MiB during preparation. GPU availability is not a substitute for host RAM. Loading the model, staging buffers and context/runtime allocations may cause paging, timeout or instability. No model was loaded to measure these requirements. Recheck resources immediately before any future attempt and defer if pressure is critical or the system unstable. No applications were closed, Windows settings changed, models downloaded or packages installed.

## Dependencies, persistence and stopping boundary

Task `de4cca0b-ba2f-43ba-8281-93a0d508c300` depends on research task `13658fc7-4bf3-4a8d-a5d3-2fd275dd2631`. The prerequisite is completed and satisfied by the exact successful research execution/latest verification above. `DependencyService.explain` classifies the synthesis task as **ready**, with **approval_required=true**. This classification means dependencies are satisfied; it does not authorize execution. The separate CEO approval remains pending and cannot be consumed in this state.

Fresh-process audit confirmed:

- Saved approval status is pending, with no decision timestamp or execution ID.
- Current recomputed proposal/fingerprint equals the persisted request.
- No synthesis execution or synthesis artifact exists; no inference claim was created.
- Original project/research/configuration/capture/execution/verification rows and previous collection approval are unchanged.
- All pre-existing managed JSON artifacts and other SQLite3 databases retain their original hashes. The isolated Stage 3.1 database changed only for the authorized task/configuration/dependency/approval preparation and associated events.
- Production source/tests and independent verification logic were not edited. No new test-suite result is claimed; latest full regression result remains 136 passed from Stage 3.2, with the later 11 offline passage checks recorded in Stage 3.3.

Inspect the actual durable pending request without invoking a model:

```powershell
.\.venv\Scripts\python.exe -m orion --database data/m10-stage3-retry/validation.sqlite3 --log-dir data/m10-stage3-4/logs approvals get 4e502cb1-c761-4f57-8072-c2e2de5ee549
```

Full private-runtime copies of the inspected operation, exact proposal, pending request and audit are retained under ignored `data/m10-stage3-4/`; source evidence remains in its original managed location. The approval binds the exact operation and model settings. Changing evidence, model configuration, selection, dependency or material project/task snapshot can invalidate it; re-inspect before any decision/execution rather than assuming the fingerprint is still current.

## CEO decision requested — STOP

Pending request **`4e502cb1-c761-4f57-8072-c2e2de5ee549`**, task **`de4cca0b-ba2f-43ba-8281-93a0d508c300`**.

Fingerprint: **`8d30a3bea288d65f4664e5a205e1bd568ed9addb9134a06447dd47db467821bf`**.

Proposed authorization: **one** real `qwen3.5:2b-q4_K_M` synthesis using the verified 12 original passages, context 4096, output 1536, provider/worker timeout 60 seconds, no retries and no downstream execution. Low available RAM and unverified real-model schema/token compatibility remain material risks.

**No approval or execution has been performed.** Per Stage 3.4's strict stop condition, await a fresh explicit CEO decision on this exact request before recording any approval or attempting inference. A fresh resource check is still required before any authorized attempt.
