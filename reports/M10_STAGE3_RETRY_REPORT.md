# M10 Stage 3.1 — Focused collection report

Date: 2026-10-31 (Asia/Calcutta). **Collection quality targets met for a scoped documentation comparison; synthesis not configured or performed.**

## Objective and approved configuration

Exact discovery query: `retrieval augmented generation`.

Broader objective: understand RAG architecture, retrieval strategies, evaluation methods, advantages, limitations and practical implementation trade-offs. This objective is retained in the project/task descriptions; the concise query was explicitly configured and disclosed in the CEO approval request.

The existing research-collect worker ran once in isolated `data/m10-stage3-retry/validation.sqlite3`, with logs and managed artifacts in that same directory. Crossref maximum 5 records; GitHub maximum 5 repositories; READMEs enabled; maximum 7 HTTPS requests; 524,288 bytes per response; 65,536 decoded README bytes; 8-second request timeout; 60-second worker deadline. No automatic retries or arbitrary URL fetching occurred.

Project: `57b1cb0c-8f39-4c63-acf3-91eb10cb9662`.
Task: `13658fc7-4bf3-4a8d-a5d3-2fd275dd2631`.
Operation: `b51ee88b-660b-438d-b411-004c9da64867`.
Approval: `c8b65dea-23d9-4f34-a3b6-caef7642e1e0`.
Fingerprint: `8458ad7c26cc3fb2903d490a82792db1fe5598038c15300b31b5cb97bae4d4e6`.
Execution: `1614e92f-45f7-4161-8672-73de5cfd3f93`.

The CEO explicitly approved the focused request. The normal approvals and execution CLI recorded and consumed that approval; the preceding Stage 3 approval was not reused.

## Provider and README outcomes

Both search requests and all five README requests returned HTTP 200. Crossref returned five records; GitHub returned five repositories with incomplete_results=false. All seven approved requests were used. No provider errors, README decoding/size failures or timeouts were recorded. Every README was captured successfully within the existing decoded-byte cap.

Execution started at 2026-10-30 18:43:27.365151 UTC (October 31, 00:13:27 IST) and finished at 18:43:35.022663 UTC: **7.657512 seconds**. API captures span 18:43:27.778201 to 18:43:34.365661 UTC. The original packet retains every capture timestamp and fixed API URL. Linked documents, images, notebooks, papers and repositories mentioned within the READMEs were not fetched.

| Stable ID / original source URL | Returned title or repository | Captured content |
| --- | --- | --- |
| [doi:10.5040/9781350865778](https://doi.org/10.5040/9781350865778) | Master Retrieval-Augmented Generation (RAG) Systems | Metadata/title only; no abstract |
| [doi:10.1002/9781394374717.ch03](https://doi.org/10.1002/9781394374717.ch03) | Retrieval‐Augmented Generation | Metadata/title only; no abstract |
| [doi:10.1002/9781394374717.ch07](https://doi.org/10.1002/9781394374717.ch07) | Graph‐based Retrieval‐augmented Generation | Metadata/title only; no abstract |
| [doi:10.5040/bci-0kgd.ch-1](https://doi.org/10.5040/bci-0kgd.ch-1) | Why Retrieval Augmented Generation? | Metadata/title only; no abstract |
| [doi:10.59350/q2pq3-0fv85](https://doi.org/10.59350/q2pq3-0fv85) | Efficient Information Retrieval and Response Generation with Retrieval-Augmented Generation (RAG) | Abstract: 468 characters |
| [repository:866513204](https://github.com/HKUDS/LightRAG) | HKUDS/LightRAG | README: 52594 bytes |
| [repository:778431525](https://github.com/microsoft/graphrag) | microsoft/graphrag | README: 5099 bytes |
| [repository:672002598](https://github.com/weaviate/Verba) | weaviate/Verba | README: 33486 bytes |
| [repository:753591102](https://github.com/alfredodeza/learn-retrieval-augmented-generation) | alfredodeza/learn-retrieval-augmented-generation | README: 4911 bytes |
| [repository:756142546](https://github.com/SciPhi-AI/R2R) | SciPhi-AI/R2R | README: 4692 bytes |

Four Crossref records have no abstract. The remaining 468-character abstract provides only a broad topic description. Publication titles are not technical findings. The GitHub READMEs provide most of this packet's useful evidence. README length alone is not a quality measure.

## Evidence quality review

Review used the actual captured README text and located technical sections; no model was used to evaluate the packet. The following are descriptions of what the documentation states, not independent software validation.

- **LightRAG:** documents graph-plus-vector organization, local/global/hybrid/naive/mix retrieval modes, four chunking strategies, reranking, four storage roles and storage-memory limitations. Its meaning of hybrid combines local/global graph retrieval, whereas Verba and R2R describe semantic-plus-keyword hybrid search; these terms must not be conflated. The README discusses RAGAS/context precision and contains an author-reported performance table for several domains and baselines. It also contains hardware, latency and scaling claims that were not independently tested.
- **GraphRAG:** describes an LLM-based pipeline that extracts structured data from unstructured text, warns about indexing cost and recommends prompt tuning. Much of its evaluation and methodology detail is in linked documents that were not captured. README links alone are not evidence of those documents' contents.
- **Verba:** documents semantic-plus-keyword search, token/sentence/semantic/recursive chunking and other formats. It distinguishes implemented features from planned reranking/evaluation and out-of-scope graph/agentic features. Its known-issues section reports a Windows limitation for embedded Weaviate and single-user scope; these are documentation claims, not a current compatibility test by Orion.
- **learn-retrieval-augmented-generation:** describes the pipeline from data import through sentence-transformer embeddings and in-memory Qdrant to LLM generation. This is useful educational documentation; referenced notebooks and code were not inspected or executed.
- **R2R:** describes REST API integration, semantic-plus-keyword search with reciprocal rank fusion, entity/relation extraction and document operations. Claims such as production readiness or state-of-the-art quality are marketing assertions, not established by this collection.

| Quality target | Result and limit |
| --- | --- |
| At least two substantive technical sources | Met: LightRAG and Verba contain specific retrieval/chunking/configuration details; R2R and the tutorial add implementation context. |
| At least one source discussing evaluation or measured results | Met: LightRAG includes evaluation-related discussion and an author-reported comparative table. Full experimental method and replication evidence were not captured. |
| At least two useful repository descriptions/READMEs | Met: five READMEs retrieved, with at least two providing substantial technical detail. |
| Enough evidence for meaningful comparison | Met for documented architecture, capabilities, terminology and stated limitations. Not sufficient for an independently verified performance ranking or a deployment recommendation for this laptop. |

One concrete numerical check: the captured LightRAG table reports agriculture comprehensiveness as 32.4% for NaiveRAG and 67.6% for LightRAG. These are source-reported table entries; do not relabel them as accuracy, speedup or reproducible measurements without the missing methodology. The same table includes a mixed-domain comprehensiveness comparison of GraphRAG 50.4% versus LightRAG 49.6%, so an unqualified claim of superiority on every metric would conflict with the captured table. No stars or fork counts were used to establish software quality.

## Independent verification and immutability

Initial verification `e25daa40-d441-473b-bbf3-1327545e9830`: **passed**.
Explicit verification from a new CLI process `7d490c72-062a-4cf9-88eb-882e33e6f68b`: **passed**.

Checks covered artifact and operation digests, captured responses, capture digest, independent schema/provenance and unchanged packet bytes. A further fresh process reread both verification records, the successful execution and its consumed approval. It found one execution, zero synthesis configurations, zero synthesis runs and zero inference claims.

Artifact: `data/m10-stage3-retry/artifacts/1614e92f-45f7-4161-8672-73de5cfd3f93.json`.
Packet SHA-256: `fca20fd13cf7c2f0ab4a3036c5d85c0ea8ed0bd956eb85355ac1973ffe923827`.

The previous Stage 3 packet still has SHA-256 `ef51bb28ee21200164619716a406a001f73fc779b1d6790c17163ec0e8910bc4`. Neither packet was modified. Verification establishes correspondence with captured provider data, not the truth of all source claims.

| Source ID | Original evidence SHA-256 (metadata and captured evidence) |
| --- | --- |
| doi:10.5040/9781350865778 | `dc0bbecd00789111808c4794a343677b1df24b4db3641b1589510afa5a0d9589` |
| doi:10.1002/9781394374717.ch03 | `58bb9ed29c3c13860498f5d98d441314976f2dc8b26a5bea34ce84d959edff7f` |
| doi:10.1002/9781394374717.ch07 | `65fe726fd544012119391960ec4ff5cf735f37dc191d3d1dca6273f8043af786` |
| doi:10.5040/bci-0kgd.ch-1 | `73df71719fbb235f2dae1707cd8e50be62854cdebaeb584d0207367e8aa1f328` |
| doi:10.59350/q2pq3-0fv85 | `8ec38c2626055dbfb8b675326f55e8f460662b48bf394f8159d2f5457ff66cc4` |
| repository:866513204 | `b612b72cd118658f1ce6256bef40ece753103a2e7e13c34ddfbc7e9a51a28df3` |
| repository:778431525 | `ce3f9c9da5e936a69d7528f2c3c4fe1f417fd91ff0a9814a4f97c73ed65dcc83` |
| repository:672002598 | `1872a7c0af47fa384b386cf6cacce39ac293ed73bf252c05f06e150a1e30e88a` |
| repository:753591102 | `ab0fed96822bbfccf6720b89717d4a52d6baf04da315af476dc64720a72f4cee` |
| repository:756142546 | `5d4bd9af7346bf517c4d69b3382dce1da88cd8b9d06a8505b949cae8de20f9f5` |

## Whether synthesis is justified

The original packet now supports a narrowly scoped, source-attributed comparison of documented approaches. It does not establish a best-performing technology. A future synthesis must retain uncertainty about missing abstracts/full papers, author-reported measurements, absent benchmark methods and untested implementation claims.

There is an important delivery constraint: the current synthesis projection includes only leading excerpts (maximum 2,000 characters per evidence field), and its prompt budget also includes all record metadata and schema. In this captured LightRAG README, the About section begins at character 15,404, query modes at 22,103, evaluation discussion at 5,129 and performance-table section at 38,933. Verba's hybrid-search entry begins at 7,730 and chunking table at 8,947. Those useful sections would be absent even from the maximum leading excerpt. A rich saved packet therefore does not mean the current model input will be rich enough.

No synthesis configuration or projection was created in this stage, as instructed. A later preparation step must review how relevant excerpts can be supplied with original source IDs, exact offsets and digests within the existing context limit. It must not silently rewrite the packet, treat an informal summary as verified evidence, or increase context. Any necessary projection change requires a separately scoped implementation and validation before requesting model execution approval.

## Boundaries, checkpoint and remaining work

The previous Stage 3 report was committed and pushed separately as `f95df8eeac1ffe24856fe85eff62418a5cb58021`; remote main was verified at that checkpoint. This retry report is saved locally. Runtime databases, captures, logs and artifacts remain ignored. No source files changed and the previous 121-test result was not rerun or relabeled as a new run.

No AI inference, synthesis configuration/execution, generated-code execution, model download, new connector, automatic retry or production-data change occurred. Instructions and code examples inside READMEs were treated as untrusted text and not executed. Stop here: a separate CEO decision is required for the next synthesis experiment.
