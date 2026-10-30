# M10 Stage 1 — Offline intelligence evaluation

Date: 2026-10-30. This checkpoint contains offline software changes and deterministic tests only. **No live Ollama, chatbot, or synthesis inference was run during Stage 1.**

## Baseline

The preserved M9 validation report records three real local inference calls. The one research synthesis failed independent verification because the model cited `limitations`; it also gave GraphRAG 38,672 forks instead of the captured 3,867, described three sources while listing four, and made unsupported comparisons and maintenance claims. Its planning proposal omitted integration prerequisites and had subjective criteria. Available system RAM reached 11.4 MiB in a sample. Before these Stage 1 edits, the full suite passed **117 tests** in 118.443 seconds.

The real failed response remains unaltered in the validation report and ignored runtime evidence directory. Production database and source artifacts were not changed.

## Offline evaluation set

`evaluations/m10_offline_cases.json` contains **16 fixed cases** with input, expected properties, failure conditions, deterministic checks, and human review criteria. It covers exact output shape, valid/invalid citation IDs, GraphRAG/LightRAG numbers and attribution, publication metadata versus full text, repository descriptions versus code, popularity versus quality, comparability, withholding recommendations, planning dependencies and measurable acceptance, hardware units, and unresolved assumptions.

Deterministic checks cover JSON shape, identifier membership, numeric copying, and dependency graph structure. Entailment, evidence relevance, task completeness, comparability, and feasibility remain human-reviewed. No LLM is used as judge.

## Changes

- `src/orion/synthesis.py` now creates a per-request structured output schema whose source reference fields enumerate exactly the source IDs in that operation's verified evidence projection. Its prompt now calls out the observed invalid label citation, demands preservation of supplied numbers, separates publication metadata and repository descriptions from full text/code, and bars popularity-based quality or cross-category metric claims.
- The existing local citation/provenance verifier is unchanged and remains authoritative. Schema-constrained output does not establish factual correctness.
- `src/orion/context.py` now gives general planning guidance to include real integration prerequisites, testing/verification and relevant packaging work, measurable acceptance criteria, and separate system RAM, GPU VRAM, model file size, and context length. It contains no finance-specific task graph. Existing plan validation and human approval are unchanged.
- Four deterministic regression tests cover rejection of the `limitations` citation, packet-specific citation enums, the recorded GraphRAG 3,867 versus 38,672 error, and general planning guidance.

## Tests and demonstrated scope

Post-change command: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -q`.

Result: **121 passed, 0 failed, 0 skipped**. The original 117 tests remain passing; four offline regression tests were added. Fixture providers are explicitly test-only and do not represent reasoning quality.

These tests demonstrate that the provider receives only packet IDs as allowed citation values and that existing independent checks still reject fabricated references. They do not show that Qwen will obey the constraints, preserve numbers, make sound comparisons, or produce a superior plan.

## Remaining limits and Stage 2

No real model evaluation, fresh research collection, enriched evidence synthesis, planning quality comparison, latency measurement, or before/after analytical quality measurement was performed. The Qwen 2B model may still hallucinate or copy numbers incorrectly; deterministic schema validation cannot establish entailment. Hardware remains memory constrained.

Stage 2 requires a separate explicit CEO approval before any live inference. The proposed bounded evaluation is one request each for a structured plan, a citation-constrained synthesis over meaningful verified evidence, and a numerical fidelity task (three calls maximum, sequential, no retries). It must use a separate validation database, existing `qwen3.5:2b-q4_K_M`, context 4096, output 2048, no downloads, and the normal approval/execution workflow for synthesis. At approval time, record available RAM and whether any applications would need to close. No applications have been closed. If freeing RAM requires closing applications, ask separately before doing so. Stop on provider failure, timeout, stale/missing approval, or invalid verification; do not repeat synthesis to obtain a pass.

## Git checkpoint

Only source guidance/schema changes, deterministic tests, the evaluation dataset, and this report/README entry are included. Runtime DBs, logs, generated artifacts, secrets and private user data are excluded. The earlier `ORION_REAL_AI_VALIDATION_REPORT.md` is retained unchanged.
