# M10 Offline Intelligence Evaluation

This fixed 16-case dataset combines deterministic checks and documented human review. It captures the October 30 live synthesis errors (unknown `limitations` reference, GraphRAG fork count 38,672 vs recorded 3,867, source miscount, incomparable metrics) and planning/hardware weaknesses. The original real response and evidence remain preserved in the validation report and ignored runtime artifacts.

Cases cover format/instruction following, citation membership and attribution, exact numbers, evidence type, popularity vs quality, unsupported comparisons, uncertainty, dependency completeness, measurable criteria, hardware units, and unresolved assumptions. Deterministic validators should check parseability, exact keys, source-ID membership, numeric label/value association, and dependency graph structure. Semantic judgments (entailment, relevance, comparability, completeness, feasibility) require human review against each case's rubric; do not use another LLM as the sole judge.

No cases contain a model answer treated as ground truth beyond the captured source values. Dataset: `evaluations/m10_offline_cases.json`. This stage performs offline regression only; no live inference has been run.
