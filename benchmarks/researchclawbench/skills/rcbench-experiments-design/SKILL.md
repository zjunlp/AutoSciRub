---
name: rcbench-experiments-design
description: Map ResearchClawBench instructions, relevant public-source results, and supplied data into an executable evidence rubric. Use for experiment planning or repair while preserving complete comparisons, method fidelity, and figure semantics.
---

# ResearchClawBench Experiment Design

Read `INSTRUCTIONS.md`, `.rcbench/profile.yaml`, `outputs/initial_rubric.json`, and `outputs/grounding_research.json`. Inspect `data/` and relevant supplied code; use `ENVIRONMENTS.md` when present. Never read hidden checklists, `target_study` material, other tasks' runs, or judge feedback. Keep supplied files unchanged. Do not run full experiments during planning.

Write `outputs/refined_rubric.json`, including data profile and execution order, using [../rcbench-workflow-controller/references/contracts.md](../rcbench-workflow-controller/references/contracts.md). Avoid repetitive planning documents.

1. Inventory relevant files, schemas, shapes, units, labels, conditions, identifiers, and joins. Select a user-prepared profile environment, record its executable, and perform a small import precheck.
2. Recheck source identity and scope against the raw instruction. Preserve every instruction `I` ID and relevant result-contract `P` ID in the execution mapping. An adjacent method cannot silently become the intended method.
3. Classify evidence routes as `direct`, `transparent_surrogate`, or `context_only`. Specify method, data, complete baseline/condition matrix, metric definitions, settings, and evidence-bounded conclusion. Keep required comparison cells explicit.
4. Give each rubric item an `R` ID, `requirement_ids`, `source_evidence_ids`, and `priority: core | supporting`. Include method signatures and `must_not_substitute` constraints. Each core item has at least one required artifact. Artifact objects state output paths, form, panels, axes/columns, units, series/groups, and scientific question; a proof or report-only obligation may use a proof file or `report/report.md`.
5. Create `core_completion_gate` entries for every instruction requirement and applicable core result. During planning use `planned`, `partial`, or `blocked`; during execution use `in_progress` as appropriate. Reserve `pass` for executed and inspected evidence. Feasibility is not execution success.
6. Order pilots and core comparisons before supporting overview, optional ablations, or robustness work. Use `claim_limits` to constrain unsupported conclusions, not to waive requirements.

A reconstruction closes a core row only when it preserves the required mechanism, conditions, comparison, metric, and scientific question. Label reconstructed/simulated data; never present them as measurements, original posterior samples, or full training outputs. A generic classifier/regression, pooled curve, single case, or incomplete baseline set cannot replace the requested comparison.

Preserve scientific artifact forms: maps, paths, attention structures, workflow evidence, and multi-panel comparisons cannot automatically become convenient bar charts. Treat `workflow.max_figures` as a presentation budget; combine readable related panels without dropping evidence.

Pilot each core experiment. For opposite or implausible reference behavior, check initialization, objective/target, split, normalization, units, sign, metrics, and plotting transformations; rerun affected computations and record the evidence. Expected directions are hypotheses. Genuine contradictory results may pass after these checks.

Before execution, check every raw requirement and applicable source ID maps to concrete evidence, artifact specifications cover the complete matrix, and feasibility gaps remain visible. Run the controller's `check --workspace . --phase plan`. A planned or existing surrogate file alone cannot establish completion.
