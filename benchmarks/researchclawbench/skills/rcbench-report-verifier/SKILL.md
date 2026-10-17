---
name: rcbench-report-verifier
description: Verify a ResearchClawBench report against original instructions, relevant public-source obligations, executed outputs, and figure semantics. Use after reporting and repairs to detect omitted experiments, weak substitutions, unsupported claims, and inconsistent verdicts.
---

# ResearchClawBench Evidence Verifier

Read raw `INSTRUCTIONS.md`, the three planning JSON files, `report/report.md`, generated results, and figures. Inspect relevant public sources; retrieve missing evidence within configured budgets. Never read hidden checklists, `target_study` material, other tasks' runs, or judge feedback.

Before trusting rubrics, independently re-enumerate obligations from the raw instruction and task-relevant source captions, tables, methods, and public code. This is a fresh source-based check, not a claim that another agent reviewed the work. Inventory method, condition/baseline matrix, metric, sample/setting, numerical comparison, artifact form, panel role, axes/columns, units, and series. Map each obligation to actual evidence and a report location. An omission in the rubric must remain visible.

## Checks

- **Scientific validity:** Verify inputs, computation, controls, metrics, units, and claim support. Trace measurements to generated files; distinguish literature context and reconstructions. Verify evaluator-facing figures are under `report/images/` and referenced in `report/report.md`; essential evidence must appear in the report and its figures, not only in auxiliary files.
- **Instruction completion:** Check every original requirement, including newly discovered rubric omissions. Limitations cannot replace feasible required experiments.
- **Source identity and protocol coverage:** Recheck source scope and matching signatures. Track source reproduction separately from task completion. No reliable source match alone does not fail valid instruction-led work; explicit reproduction and already applicable core obligations cannot be waived. If review disputes grounding, transparently correct/replan the grounding and downstream mapping instead of silently changing final applicability.
- **Core completion:** For every instruction `I` ID and applicable core source `P` ID, locate executed data, report discussion, and the required artifact. A partial matrix, adjacent method, literature-only discussion, or context-only surrogate does not close an obligation.
- **Semantic artifacts:** Open every core figure and inspect plotted data. Check forms, panels, axes/columns, units, series, conditions, encodings, and scientific question; inspect tables for complete comparisons. Existence and visual resemblance alone are insufficient.

Reference values/trends are diagnostics. Large or opposite results require documented protocol, implementation, split, normalization, unit/sign, metric, and plotting checks, with affected computations rerun. Correct contradictory findings can pass; literature agreement is not mandatory.

## Verdict and direct repair

Write `outputs/report_rubric_check.json` using [../rcbench-workflow-controller/references/contracts.md](../rcbench-workflow-controller/references/contracts.md). Separate `scientific_validity_pass`, `task_completion_pass`, and `protocol_coverage_pass`. `overall_pass` requires scientific validity and task completion, including all applicable core obligations. Source identity is not a universal success gate.

A failed core check, unresolved core fidelity gap, unsupported claim, missing required artifact, or partial core form/panel/axis/series match prevents an overall pass. Keep verdicts consistent with per-item evidence. Record supporting source-protocol gaps separately when they are outside task completion conditions.

`required_fixes` lists unresolved required work and must be empty for an overall pass; keep optional improvements separate. Each `required_fixes` action names an obligation and the computation/result file/figure/table that directly closes it. Prioritize wrong source/method, missing artifact, incomplete comparison, incorrect artifact semantics, setting/metric, unsupported claim, then presentation. An overview, generic robustness test, or unrelated ablation cannot repair a missing core result. Follow `workflow.max_revision_rounds` and reverify each repair.

Run the controller's `check --workspace . --phase final`; resolve structural contradictions before delivery. Report blocked IDs when available resources cannot close them. Structural validation cannot substitute for scientific judgment or visual inspection.
