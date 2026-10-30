# Orion real AI integration and validation

Validation date: 2026-10-30. Inference timestamps below are UTC.

**Result:** Orion demonstrated genuine local AI conversation, a persisted structured project proposal, and a real model response to verified research evidence. The research synthesis was correctly rejected for invalid citations. This exercise establishes functioning integration and a working rejection boundary; it does not establish a reliable research analyst or autonomous company.

## 1. Baseline and environment

- Repository: https://github.com/JEFFIN-alt/orion, branch `main`.
- Local HEAD and remote `main` both verified as `556d8bddb8d576b0081a952540af4d6e25171374`, `Milestone 9: evidence-grounded research synthesis`.
- Working tree was clean before validation. No application source, tests, dependencies, or database schema changed. This report is the only new non-ignored repository file; no commit or push was made during validation.
- Baseline command: `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`.
- Actual result: **117 passed, 0 failed, 0 skipped**, 126.088 seconds. The regression suite uses deterministic fixtures for model-dependent tests; the three live requests reported separately below used the real Ollama provider. Source files have not changed since that test run.
- Existing Python: 3.12.10. Windows CPU: Intel Core i5-12450H, 8 cores/12 logical processors. Usable physical memory: approximately 7,832.5 MiB. GPU: NVIDIA RTX 2050, 4,096 MiB VRAM.
- Initial available RAM was approximately 619.4 MiB; initial aggregate GPU memory was 658 MiB. This was already a busy, memory-constrained system.

The existing provider interface, factory/configuration, Ollama adapter, conversation/context handling, synthesis worker, approval/execution services, and independent verifier were inspected. The production database had no research-collection execution to reuse. It was not overwritten. A separate validation database was created from a safe backup of the existing genuine M8 research demonstration, with its managed artifacts copied into the validation directory.

## 2. Provider configuration and connection

Ollama's existing service responded at `http://127.0.0.1:11434`. Its API reported version **0.40.13** and installed model **qwen3.5:2b-q4_K_M**, parameter size **1.9B**, quantization **Q4_K_M**, model file size **1,945,781,358 bytes**. Installed digest:

`1e2d21a4f03ab9e4a9c1976a4b7e88f21de61d65f2c5485d8fde8942be73f1e7`

Temporary process environment variables used the existing supported names:

| Variable | Value |
| --- | --- |
| ORION_AI_PROVIDER | ollama |
| ORION_AI_ENDPOINT | http://127.0.0.1:11434 |
| ORION_AI_MODEL | qwen3.5:2b-q4_K_M |
| ORION_AI_CONTEXT | 4096 |
| ORION_AI_MAX_OUTPUT | 2048 |
| ORION_AI_TIMEOUT | 60 |

No global Windows settings changed. No model or software was installed, and no second Ollama server was started. The existing adapter uses temperature 0.2, `think=false`, and `keep_alive=0`; this was unchanged. The active-model API confirmed context 4096 and model VRAM allocation of 1,626,865,662 bytes during inference. This API allocation differs from aggregate GPU memory measurements below.

All three requests used the existing production provider abstraction. Responses persisted accurate provider/model identity and elapsed time. No fixture or canned fallback supplied these responses. No model-generated code was executed and no tools were exposed to the model.

## 3. CEO browser interaction and planning

The existing CLI started the local chat interface at `http://127.0.0.1:8765` with `--database data/real-ai-validation/orion.sqlite3` and a separate log directory. The browser submitted the requested seven-day, zero-budget, local Windows personal-finance objective verbatim using **Send message**.

The first real response took **50.156 seconds**. It understood transaction management, budgeting, local persistence, GUI, and spending analysis, and proposed Python/PySide6/SQLite. It did not claim the application had been built. However, it proposed downloading a different 7B model with an unsupported approximately 2 GB RAM estimate, produced unnecessary sample code, and used an unsupported personal greeting. Its code sample constructs a QWidget before QApplication and calls the event loop on the widget; it was preserved as text and never executed. Initial objective text did not contain the hardware/model constraints, which limits attribution of its model choice to instruction failure.

A second browser request used **Propose plan**, repeated the objective, and explicitly added 8 GB RAM, RTX 2050 4 GB, the existing model name, no downloads, four concise tasks, dependencies, acceptance criteria, and no approval or execution. It returned in **40.688 seconds**, passed Orion's planning schema, and persisted proposal:

`52aefbd0-4551-4c56-9304-61bc6fe835b8`

The proposal remains **proposed**, with no approval, project creation, or task execution. It chose the installed model once explicitly constrained. Full actual planning JSON appears in Appendix A.

Its four tasks were environment setup, database schema, GUI, and AI integration. All three latter tasks depend only on setup. The GUI's own persistence and AI-display acceptance criteria require integration with the other tasks, but the dependency graph does not express that. There is no separate integration/testing/packaging task or concrete seven-day allocation. Criteria mix observable checks with subjective judgments such as reasoning being logical rather than gibberish. It conflates model parameter size with context limits, and GPU memory with system RAM. Its confidence threshold is not calibrated evidence of correctness.

### Comparison with the earlier manual response

The CEO supplied the earlier Qwen response in this conversation. It was not independently rerun, and no latency/resource comparison is available for that earlier test. It proposed five tasks: setup, SQLite schema, rule-based categorization, Windows GUI, and packaging. Its dependency sequence explicitly linked schema, categorization, GUI, and final testing/package creation. It was more conservative about seven-day feasibility and preferred a rule-based first version. The current Orion proposal provides a persisted, schema-checked approval object and more explicit AI integration, but its dependency reasoning is worse. The earlier response also had broad acceptance criteria and did not make budgeting implementation explicit. Different prompts and context prevent treating this as a controlled model benchmark.

## 4. Research evidence and approval

Reused actual M8 research execution:

`660a40da-3325-4000-8504-c7195c8d63a5`

Question: **retrieval augmented generation**. Original capture date: 2026-10-29. Both Crossref and GitHub recorded successful outcomes, returning two records each. No fresh external collection was needed or performed during this validation. These are recorded observations, not assertions about today's live repository counts.

Latest required source verification was passed: `7d59b433-4c4b-4a32-bb71-4e978dcca0de`. Historical verification records, including an earlier failed tampering demonstration and subsequent passed verification, were preserved. Eligibility was evaluated against the actual latest verification and current artifact bytes.

| Stable source ID | Captured material |
| --- | --- |
| doi:10.5040/9781350865778 | Packt publication metadata/title; no abstract or author |
| doi:10.1002/9781394374717.ch03 | Wiley publication metadata/title; no abstract or author |
| repository:866513204 | HKUDS/LightRAG metadata and short description; 40,418 stars, 5,738 forks |
| repository:778431525 | microsoft/graphrag metadata and short description; 36,489 stars, 3,867 forks |

No full papers or README content were available. This is adequate to exercise provenance and integration, but insufficient for a substantive comparison of technical approaches. All four records entered the bounded projection. Configuration allowed at most 10 sources, 80 characters per evidence excerpt, 12,000 prompt bytes and 16,000 response bytes. The existing context-derived prompt cap further limited input to 8,192 bytes. No current evidence field required excerpt truncation; all omission maps were empty. Selected metadata and captured snippets are still a projection, not complete source documents.

Original and copied evidence packet SHA-256 remained identical after synthesis:

`15dc29f36a2f39f417e0072dc4fac13449983bcd6d4029b9be8519a051c83cb9`

New synthesis task: `a5dddcdb-7408-48df-8e03-7dbfda0ba748`.

Approval request: `d13bb733-ca97-415f-9431-0af1a5a31c13`, bound to source, digest, configuration and model. Work stopped at the CEO boundary. The CEO explicitly answered **Approve this synthesis execution** for one bounded execution. The normal ApprovalService recorded the decision; the normal ExecutionService consumed it. No follow-on tasks or retries were automatically authorized or run.

## 5. Actual synthesis and independent verification

Execution: `b0b8b113-4cee-4158-b6e6-430e52b6ff6b`.

Started 17:58:34.643 UTC; finished 17:59:33.017 UTC. Model elapsed time: **57.610 seconds**. Measured service-call wall time: **58.419 seconds**, close to the 60-second limit. The provider completed without timeout or provider error. Full actual response appears in Appendix B, unchanged.

**Final execution status: failed.** The model produced valid JSON matching the strict analysis schema, but cited `limitations` as a source ID in its third finding and two disadvantages. That identifier is not in the input packet. The independent verifier rejected it with `key_findings.2: unknown source ID`.

| Verification | Result |
| --- | --- |
| Initial: 78a308aa-ac2a-47ab-878f-7c584d4f5cdf | Failed citation/provenance check |
| Explicit re-verification: a808fe82-9b41-4fff-978d-dfcc30ff3893 | Failed with the same reason |

Both records persisted and were inspected from a subsequent process. Operation digest, artifact digest, envelope schema, execution binding, timestamp, provider completion, response metadata, upstream digest, evidence projection and strict analysis schema passed. Citation/provenance validation failed. The result field `output_validated=true` must not be read as overall success: `verification_status=failed`, `independent_evaluation=false`, and execution `status=failed` are decisive.

Output artifact SHA-256:

`87a521bdb97d6f38c6ec2b8d3392b46b2a8f09d60cc1f70e7de6a9e680c8df8e`

Human review found additional defects that structural citation validation does not certify:

- Summary says three sources while listing four source IDs.
- GraphRAG forks are misstated as 38,672; the supplied evidence says 3,867.
- Publication records are called academic papers without supporting full text or publication-type evidence in the projection.
- Repository popularity is compared with academic-paper popularity without comparable measurements.
- Repository existence is used to imply active development and community engagement more strongly than the captured evidence supports.
- A suggested third-party security audit is poorly aligned with the zero-budget goal.

The model did correctly withhold a recommendation (`supported=false`) and report low confidence and missing evidence. That useful uncertainty handling does not cancel its factual and citation errors. No output was repaired, replaced, or resubmitted, and verification was not weakened.

## 6. Performance measurements

Samples were taken approximately every 2 seconds using Windows system memory/CPU counters and `nvidia-smi`. Values include all system processes. They are not isolated Orion memory usage, and sampled peaks may miss shorter spikes. Adapter timings include request/model loading and generation; no token-throughput or time-to-first-token measurements were collected.

| Phase | Model seconds | Samples | Peak used system RAM MiB | Minimum available RAM MiB | Mean / peak system CPU % | Peak aggregate VRAM MiB | Mean / peak GPU utilization % |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| CEO discussion | 50.156 | 23 | 7821.1 | 11.4 | 44.6 / 79.1 | 3048 | 55.1 / 80 |
| Structured plan | 40.688 | 18 | 7330.0 | 502.5 | 48.1 / 77.8 | 2985 | 51.7 / 85 |
| Research synthesis | 57.610 | 27 | 7258.2 | 574.3 | 37.5 / 68.1 | 2981 | 51.3 / 100 |

- Real inference responses: 3/3; observed timeouts: 0/3. This small sample is not a reliability estimate.
- Structured-output parsing/schema success: 2/2 (one plan, one synthesis). Free-text chat has no JSON requirement.
- Accepted synthesis executions: 0/1. Independent verification attempts on that same output: 0/2 passed; these are not two model trials.
- The RAM minimum shows severe transient memory pressure. Paging, per-process peak allocation, thermal behavior and sustained performance were not measured, so latency cannot be attributed to a specific cause.

## 7. Capability scorecard

Engineering assessments on this small observed sample, not formal benchmarks:

| Capability | Score / 10 | Evidence |
| --- | ---: | --- |
| Instruction following | 6 | Honors explicit installed-model constraint and format; invents citation ID |
| Planning | 5 | Useful decomposition but missing integration/packaging and schedule detail |
| Dependency reasoning | 4 | Valid graph with important integration prerequisites omitted |
| Technical understanding | 4 | Plausible stack, weak memory/context explanations and unexecuted flawed sample code |
| Research comprehension | 3 | Miscounts sources, changes a number, mischaracterizes publications |
| Synthesis quality | 3 | Mostly repeats limitations; unsupported comparisons |
| Citation integrity | 3 | Mostly real IDs, but invents `limitations`; execution rejected |
| Uncertainty handling | 7 | Explicit low confidence and no defensible recommendation |
| Output reliability | 6 | Both structured responses parse; synthesis fails semantic provenance policy |

## 8. Diagnosis and next milestone

Provider integration worked in all observed calls. No application defect requiring a source patch was established. Application verification correctly blocked an invalid report; it cannot prove factual accuracy even for valid IDs.

Model capability is a demonstrated limitation: numerical copying, category distinctions, dependency reasoning and valid citation choice were unreliable. Prompt/context quality also matters: explicit hardware constraints improved the second plan; thin metadata prevents substantive research comparison. The 4,096 context and 2,048 output settings completed these responses, with no observed malformed/truncated JSON; token-level context loss was not measured. Output limits should not be blamed for errors without additional evidence. Hardware pressure and the narrow deadline margin limit comfortable repeated use.

Recommended next milestone: **bounded analyst quality and engineering-plan review**.

1. Keep the human approval boundary. Review/correct task dependencies and acceptance checks before approving any project plan. Use deterministic money calculations and rule-based categorization as the finance application's first implementation, with model suggestions subject to review.
2. Add a small reviewed evaluation set covering source-ID correctness, numerical fidelity, unsupported comparisons, and dependency completeness. Preserve this failed live response as a local regression example. Ordinary tests should remain offline and fixture-based; live quality tests should be explicitly labeled.
3. In a separately scoped change, constrain allowed citation IDs in the model-facing structured schema where supported, clarify that packet limitations are not source records, and add regression coverage. Continue independent rejection; do not rely on schema-constrained generation as factual certification.
4. Obtain meaningful bounded abstracts or README evidence through the existing research collector and normal approval process, then request fresh CEO approval for another live synthesis. A four-source metadata packet cannot justify an architecture winner.
5. Reduce unrelated background memory demand before a controlled repeat, retain one inference at a time, and measure repeat latency and memory. No applications were closed automatically. Do not simply increase context/output on this 8 GB system.
6. If evaluated results remain inadequate, retain Qwen for draft assistance and deterministic workers for calculations/provenance, with human analysis for consequential conclusions. A larger or different local model is only a candidate for a separately authorized, measured experiment within existing RAM/VRAM; this run supplies no basis to promise one will fit or perform better. No paid service or model download is required for the immediate improvements.

## 9. Completion, recovery and limits

**Completed:** environment/provider checks, full regression suite, real browser conversation, real structured proposal, verified evidence selection, CEO-approved real synthesis attempt, independent rejection, repeat verification, fresh-process inspection, digest preservation and resource sampling.

**Partial:** planning is structurally valid but needs human corrections; synthesis integration runs but analytical output is unacceptable.

**Failed:** synthesis citation/provenance acceptance and several factual fidelity checks.

**Not performed:** fresh research collection, accepted live synthesis, repeated model trials, finance application implementation, execution of model code, project-plan approval, autonomous follow-on work, controlled comparison against another model, throughput benchmarking or factual certification. The earlier manual response comparison is based solely on CEO-supplied text.

Runtime evidence remains in ignored `data/real-ai-validation/`: separate database, original/copied source artifacts, failed synthesis artifact, approval snapshots, conversation/plan records, verification history, raw resource samples and summary metrics. The original M8 packet digest and copied packet digest match. The production database was not used for experimental writes. No inference claim or running execution remained at final inspection; synthesis execution ownership is stopped, and the one approval is bound to its completed failed attempt. The local chat server remains available for reviewing the unapproved proposal; it has no active inference.

Git history is unchanged and remote `main` still matches M9. Runtime databases, artifacts and logs remain ignored. The only repository addition is this report. No credentials or private financial data were used in model prompts.

**Executive assessment:** Orion has progressed beyond a deterministic workflow engine: it can call a real local model, persist a structured plan, and run an approved evidence-synthesis request through independent validation. Today it is a useful supervised drafting and integration prototype. The observed model output does not support calling it a dependable research analyst, and the autonomous-company vision remains unachieved.


## Appendix A. Actual model planning output

Unedited response; schema accepted, proposal unapproved.

```json
{
"title": "LocalFin AI Finance App - 7-Day Proposal",
"description": "Build a free, locally running Windows application for transaction management, budgeting, and AI-powered spending analysis using the installed `qwen3.5:2b-q4_K_M` model.",
"assumptions": [
  "The user has verified that `qwen3.5:2b-q4_K_M` is installed on their system (confirmed by hardware check).",
  "The user has access to a standard Python environment (e.g., PyCharm, VS Code) and basic command-line tools.",
  "No external internet access is required for the AI inference phase once the model is loaded locally."
],
"risks": [
  "Model quantization size (2B) may limit context window length or reasoning depth compared to larger models; we will implement truncation strategies if needed.",
  "Local GPU memory usage during inference might exceed 8GB RAM if not managed carefully; we will use CPU fallback for heavy tasks.",
  "AI hallucination in categorization could lead to incorrect budgeting; we will implement a confidence threshold and manual override mechanism."
],
"unresolved_questions": [
  "How to handle multi-step reasoning (e.g., 'Is this an emergency expense?') within the 2B context window without truncating critical details?",
  "What is the exact memory footprint of loading `qwen3.5:2b-q4_K_M` on a Windows system with 8GB RAM?"
],
"tasks": [
  {
    "key": "setup-env",
    "title": "1. Environment Setup & Model Loading",
    "description": "Configure Python environment, install PySide6 for the GUI, and load the quantized model into memory.",
    "priority": 1,
    "dependencies": [],
    "acceptance_criteria": [
      "Python executable is installed and accessible from command line.",
      "PySide6 PyQt5/QtWidgets libraries are installed.",
      "The `qwen3.5:2b-q4_K_M` model is successfully loaded into RAM (verified via memory usage check).",
      "No errors occur during the initial import of the model."
    ]
  },
  {
    "key": "db-schema",
    "title": "2. Database Schema Design",
    "description": "Design and implement a SQLite schema for transactions, budgets, and AI analysis logs.",
    "priority": 2,
    "dependencies": ["setup-env"],
    "acceptance_criteria": [
      "SQLite database file is created with correct tables: `transactions`, `categories`, `budgets`, `ai_analysis`.",
      "Data types are appropriate for financial data (e.g., DECIMAL for amounts).",
      "Indexes are added on common query fields (date, category_id) for performance."
    ]
  },
  {
    "key": "gui-impl",
    "title": "3. Windows GUI Implementation",
    "description": "Develop the PySide6 application window with transaction management, budgeting views, and AI insights panel.",
    "priority": 3,
    "dependencies": ["setup-env"],
    "acceptance_criteria": [
      "Application launches on Windows without crashing.",
      "UI elements (Add Transaction, Budget List, AI Insights) are functional and responsive.",
      "Data persists correctly after closing the application.",
      "The 'AI Analysis' panel displays results for selected transactions."
    ]
  },
  {
    "key": "ai-integration",
    "title": "4. AI Inference & Validation",
    "description": "Integrate the local model to categorize expenses and analyze spending patterns, with fallback logic.",
    "priority": 4,
    "dependencies": ["setup-env"],
    "acceptance_criteria": [
      "When a transaction is added, the AI returns a predicted category and confidence score.",
      "The 'Reasoning Text' provided by the model contains logical content (not empty or gibberish).",
      "If confidence < 0.7, the system defaults to a generic 'Expense' category instead of hallucinating a specific one.",
      "A manual override button exists in the UI to correct AI predictions."
    ]
  }
]
}
```

## Appendix B. Actual model synthesis output — FAILED VERIFICATION

Unedited response. Contains invalid source IDs and factual errors discussed above; it is not an accepted analysis.

```json
{
  "schema_version": 1,
  "execution_id": "b0b8b113-4cee-4158-b6e6-430e52b6ff6b",
  "question": "retrieval augmented generation",
  "executive_summary": {
    "text": "The provided evidence consists of metadata from three external sources (Crossref, GitHub repositories) regarding Retrieval-Augmented Generation (RAG). These sources indicate the existence of academic papers and open-source implementations but do not constitute a review or certification of the RAG field itself. The data confirms the presence of literature on the topic and popular tools, but lacks any verification of their correctness, security, maintenance status, or suitability for specific use cases.",
    "source_ids": [
      "doi:10.5040/9781350865778",
      "doi:10.1002/9781394374717.ch03",
      "repository:866513204",
      "repository:778431525"
    ]
  },
  "key_findings": [
    {
      "text": "Two academic papers are identified in the evidence, one titled 'Master Retrieval-Augmented Generation (RAG) Systems' and another 'Retrieval-Augmented Generation', suggesting foundational knowledge exists.",
      "source_ids": [
        "doi:10.5040/9781350865778",
        "doi:10.1002/9781394374717.ch03"
      ]
    },
    {
      "text": "Two GitHub repositories are identified as popular open-source implementations, with 'LightRAG' having 5,738 forks and 'graphrag' having 38,672 forks.",
      "source_ids": [
        "repository:866513204",
        "repository:778431525"
      ]
    },
    {
      "text": "The evidence explicitly states that Crossref records are publication metadata and optional abstracts, not full papers, and does not constitute a factual certification of the field.",
      "source_ids": [
        "limitations"
      ]
    }
  ],
  "comparisons": [
    {
      "text": "The evidence shows two distinct academic sources (Crossref) and two distinct open-source implementations (GitHub). The Open Source implementations are significantly more popular than the academic papers in terms of forks/stargazers.",
      "source_ids": [
        "repository:866513204",
        "repository:778431525"
      ]
    }
  ],
  "advantages": [
    {
      "text": "The presence of two academic papers suggests a foundational body of knowledge exists for the field.",
      "source_ids": [
        "doi:10.5040/9781350865778",
        "doi:10.1002/9781394374717.ch03"
      ]
    },
    {
      "text": "The presence of two GitHub repositories indicates active development and community engagement.",
      "source_ids": [
        "repository:866513204",
        "repository:778431525"
      ]
    }
  ],
  "disadvantages": [
    {
      "text": "The evidence explicitly states that Crossref records are publication metadata and optional abstracts, not full papers, and does not constitute a factual certification of the field.",
      "source_ids": [
        "limitations"
      ]
    },
    {
      "text": "The evidence explicitly states that GitHub repository popularity is not proof of correctness, security, maintenance or suitability.",
      "source_ids": [
        "limitations"
      ]
    }
  ],
  "evidence_limitations": [
    "Collected provider evidence, not AI synthesis or factual certification.",
    "Crossref records are publication metadata and optional abstracts, not full papers.",
    "Repository popularity is not proof of correctness, security, maintenance or suitability.",
    "External content is untrusted data; no retrieved instructions are executed."
  ],
  "unresolved_questions": [
    "What is the current state of security for the RAG field based on this evidence?",
    "Is there a consensus on the best practices for implementing RAG systems based on this evidence?"
  ],
  "recommendation": {
    "supported": false,
    "text": "Based solely on the provided evidence, a recommendation cannot be made regarding the correctness, security, maintenance status, or suitability of Retrieval-Augmented Generation systems. The evidence only confirms the existence of literature and popular open-source implementations, but does not provide factual certification or verification of their quality.",
    "source_ids": []
  },
  "next_experiments": [
    "Request a review from an independent third-party security audit firm for specific RAG systems.",
    "Conduct a manual code review of the identified GitHub repositories to assess maintenance and security practices.",
    "Analyze the academic papers for technical depth and methodology, acknowledging that this is not a certification."
  ],
  "confidence": {"level": "low", "explanation": "The evidence consists only of metadata from external providers (Crossref, GitHub). It lacks any direct verification or analysis of the systems themselves. The explicit limitations in the source data confirm that this information does not constitute a factual certification."}
}
```
