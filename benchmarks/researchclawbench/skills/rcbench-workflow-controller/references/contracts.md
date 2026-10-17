# ResearchClawBench artifact contracts

Use this reference when writing or checking the three planning artifacts and final verdict. IDs preserve the chain **raw instruction → public result/protocol → executable rubric → measured artifact → report verdict**. Domain-specific fields may be added; keep scientific detail that affects execution. All paths below are workspace-relative. Put evaluator-facing figures under `report/images/` and reference them from `report/report.md`; files elsewhere are not automatically visible to the report evaluator.

## Common rules and completion semantics

- Goals use `G` IDs, explicit instruction requirements `I` IDs, result-contract rows `P` IDs, and execution-rubric items `R` IDs. IDs must be unique within their set; instruction and result IDs must not overlap.
- Every instruction requirement maps to at least one **core** rubric item. Every applicable core result row also maps to a core item. `source_evidence_ids` references result rows, not bibliographic citations; include public source citations separately.
- `priority` is `core` or `supporting`. A hard instruction requirement cannot be downgraded to supporting. Public sources add obligations only when relevant to the raw task, not merely because a paper contains another experiment.
- `core_completion_gate` contains every instruction `I` ID and every applicable core `P` ID. Public-paper rows are applicable when `paper_identity_gate.applicable` is true; instruction and compatible-public-source result rows remain applicable without a matched paper. Core applicability must not be silently changed after a gap appears.
- Gate statuses are `planned`, `in_progress`, `partial`, `pass`, and `blocked`. `planned` means executable work is specified, not completed. `partial`/`blocked` requires a concrete `blocking_gap`; `pass` requires executed, inspected evidence and an empty gap. The plan check rejects execution-pass claims.
- Expected directions and reference values are diagnostics, never required empirical outcomes. Preserve methods, comparisons, metrics, and artifact semantics; allow genuine contradictions after documented debugging.
- Every core rubric item has at least one required artifact; supporting items may have none. Every required artifact has a concrete `path`. Figures and tables are checked for data support and semantics, not merely file existence. A report-only obligation may reference `report/report.md`; never invent a decorative figure to satisfy a generic schema.

`paper_identity_gate.applicable` means a matched public paper supplies a strong task-protocol contract, or the instruction explicitly requires source reproduction. Its `pass` diagnoses whether identity is sufficiently supported, not whether experiments finished. An inapplicable identity gate has `pass: false` and an explanation.

`protocol_coverage_pass` records completed coverage of the applicable, verified source protocol. `task_completion_pass` records completion of the raw task and all applicable core obligations. `scientific_validity_pass` records whether generated evidence and claims are scientifically sound. `overall_pass` requires scientific validity and task completion; it is not a measure of expected leaderboard score. Applicable source obligations cannot remain unresolved while claiming task completion.

For example, an instruction requests comparing two supplied models on held-out data, with no named paper to reproduce. No reliably matching public paper is found. After executing the complete comparison with valid metrics and artifacts, identity may be `{ "applicable": false, "pass": false }`, `protocol_coverage_pass` may be false, and scientific validity, task completion, and overall pass may be true. Explain the source-reproduction limitation separately. Conversely, a task explicitly requiring a particular published mechanism cannot pass by substituting an adjacent method and declaring source identity inapplicable.

## 1. `outputs/initial_rubric.json`

Required structure:

```json
{
  "source": "instruction_only",
  "task_summary": "The requested scientific question",
  "scientific_goals": [
    {"id": "G1", "objective": "Scientific objective", "success_question": "Question answered by evidence"}
  ],
  "requirements": [
    {"id": "I1", "statement": "Exact experimental or deliverable requirement", "goal_ids": ["G1"], "instruction_evidence": "Short task phrase or location"}
  ],
  "explicit_requirements": {
    "inputs": [], "outputs": [], "methods": [], "comparisons": [], "metrics": [], "artifacts": []
  },
  "retrieval_anchors": {
    "named_entities": [], "distinctive_phrases": [], "numbers_and_conditions": [], "artifact_signals": []
  },
  "unresolved_requirements": []
}
```

All goals must have requirements. Preserve numerical settings and separate condition-specific comparisons. `explicit_requirements` is an optional compact index; it does not replace the ID-bearing `requirements` array. Record unknown protocol details instead of guessing.

## 2. `outputs/grounding_research.json`

The identity and result-contract fields below form the minimum executable connection. Other fields preserve scientific grounding:

```json
{
  "source": "task_level_grounding",
  "task_fingerprint": {"keywords": [], "research_goal": "Task-level question", "query_ids": ["q01"]},
  "candidates": [
    {"rank": 1, "title": "Inspected public paper", "url_or_path": "Public URL or permitted local path", "full_text_checked": true, "target_like_candidate": "possible", "match": {}, "evidence": [], "contrary_evidence": []}
  ],
  "most_relevant_paper": {"title": "Inspected public paper", "rank": 1, "uncertainty": "Remaining identity uncertainty"},
  "paper_identity_gate": {
    "applicable": true,
    "pass": true,
    "scope_reason": "Why this paper supplies a task-relevant protocol",
    "scientific_object_and_io": "strong",
    "distinguishing_method": "strong",
    "exact_experiment": "strong",
    "artifact_or_result": "strong",
    "contrary_evidence": []
  },
  "protocol_lock": {
    "status": "locked",
    "anchor_paper": "Inspected public paper",
    "method_signature": [],
    "experiment_signatures": [],
    "artifact_signatures": [],
    "forbidden_substitutions": []
  },
  "protocol_fingerprint": {
    "data_and_split": [], "methods": [], "baselines": [], "metrics": [],
    "sample_training_or_simulation_settings": [],
    "result_contract": [
      {
        "id": "P1",
        "priority": "core",
        "source_type": "public_paper",
        "requirement_ids": ["I1"],
        "source": "Public paper section/figure/table or public code location",
        "experiment": "Scientific comparison addressed by this block",
        "method_signature": [],
        "conditions_and_n": [],
        "baselines": [],
        "metrics": [],
        "literature_values_or_trends": [],
        "artifact_blueprint": {"form": "Scientific form", "panels": [], "axes_or_columns": [], "units": [], "series_or_groups": [], "reference_behavior": []},
        "must_not_substitute": []
      }
    ]
  },
  "cross_paper_fallback": [],
  "search_limitations": []
}
```

Use `target_like_candidate: possible | weak | no`; only `possible` denotes a verified full-text match. Match dimensions use `strong | partial | no`. Use `protocol_lock.status: locked | partial | unavailable`; `locked` requires passing applicable identity. Do not label a candidate the hidden target.

`source_type` is `public_paper`, `instruction`, or `compatible_public_sources`. Instruction-led rows must state their actual origin and preserve the instruction's question. Empty source-result arrays are permitted when no source protocol is applicable, but the initial instruction obligations still require mapping, execution, and final core checks.

Enumerate every required condition, baseline, metric, sample setting, panel/column, and numerical comparison. There is no fixed number of papers or result blocks. Do not infer source obligations from unrelated paper results. Full-text and query effort limits come from the profile, with all executed queries recorded in the query plan rather than an inconsistent duplicate list.

## 3. `outputs/refined_rubric.json`

```json
{
  "source": "experiment_design",
  "selected_environment": "base",
  "python_executable": "Prepared executable resolved from the profile",
  "import_precheck": [],
  "data_profile": [{"path": "data/input.csv", "shape_or_schema": "Inspected schema", "role": "Scientific use", "notes": "Units, IDs, joins, limitations"}],
  "rubric_items": [
    {
      "id": "R1",
      "requirement_ids": ["I1"],
      "source_evidence_ids": ["P1"],
      "priority": "core",
      "objective": "Executable scientific requirement",
      "method": "Concrete implementation",
      "method_signature": [],
      "must_not_substitute": [],
      "data_sources": [],
      "baselines_or_comparisons": [],
      "metrics_or_values": [],
      "required_artifacts": [
        {"path": "report/images/comparison.png", "form": "Scientific form", "must_show": "Required comparison", "panels": [], "axes_or_columns": [], "units": [], "comparison_groups": [], "reference_behavior": []}
      ],
      "expected_directions": [],
      "evidence_level": "direct"
    }
  ],
  "core_completion_gate": [
    {"source_evidence_id": "I1", "status": "planned", "blocking_gap": ""},
    {"source_evidence_id": "P1", "status": "planned", "blocking_gap": ""}
  ],
  "fidelity_gate": [
    {"source_evidence_id": "P1", "method_match": "exact", "condition_match": "exact", "baseline_metric_match": "exact", "artifact_semantics_match": "exact", "blocking_gap": ""}
  ],
  "evidence_matrix": [{"goal_id": "G1", "rubric_id": "R1", "comparison": "Complete condition/baseline matrix", "metric": "Definition and units", "artifact": "report/images/comparison.png", "conclusion_test": "Evidence that answers the question"}],
  "execution_order": [],
  "claim_limits": []
}
```

The example is a plan, so no completion gate claims pass. Update gates as execution progresses; final `core_completion_check.pass` must agree with whether the corresponding refined gate has reached `pass`.

`evidence_level` is `direct | transparent_surrogate | context_only`. Add `completion_mode: direct | faithful_reconstruction | context_only` and preserved/missing dimensions to gates where useful. `fidelity_gate` is a feasibility/alignment assessment, not proof of completed execution. A faithful reconstruction can close a row only when it preserves the actual requirement; a context-only surrogate cannot.

Required artifact paths are within the workspace, outside supplied inputs and forbidden evaluation material. Map all instruction requirements as core even when source evidence IDs are empty. Artifacts may serve more than one rubric item; reuse the same path consistently instead of fabricating duplicates.

## 4. `outputs/report_rubric_check.json`

The following is a nonpassing shape example; replace its entries with actual review evidence:

```json
{
  "source": "source_based_report_verifier",
  "overall_pass": false,
  "scientific_validity_pass": false,
  "task_completion_pass": false,
  "protocol_coverage_pass": false,
  "paper_identity_check": {"applicable": true, "pass": true, "matched_signatures": [], "contrary_evidence": []},
  "execution_check": {"pass": false, "missing": ["Incomplete required comparison"], "unsupported_claims": []},
  "alignment_check": {"pass": false, "instruction_omissions": ["I1 remains incomplete"], "protocol_omissions": ["P1 remains incomplete"], "wrong_or_weak_substitutions": [], "artifact_mismatches": []},
  "protocol_lock_check": {"pass": false, "unresolved_fidelity_gaps": ["Missing required comparison condition"]},
  "core_completion_check": [
    {"source_evidence_id": "I1", "pass": false, "missing": ["Required comparison"]},
    {"source_evidence_id": "P1", "pass": false, "missing": ["Required comparison"]}
  ],
  "artifact_checks": [
    {"path": "report/images/comparison.png", "present": false, "data_backed": false, "form_match": "no", "panel_axis_series_match": "no", "behavior_match": "not_comparable", "missing_elements": ["Required comparison panel"]}
  ],
  "required_fixes": [
    {"priority": 1, "obligation_ids": ["I1", "P1"], "action": "Execute the missing condition and regenerate the comparison", "expected_evidence": "Result file and complete comparison figure"}
  ]
}
```

`required_fixes` means unresolved required work. Any nonempty list prevents `overall_pass: true`; put optional presentation improvements in a separate field.

Every required artifact gets a check row, even when missing. `present` must match a nonempty actual file. `data_backed` and semantic-match values require agent inspection. Use `form_match` and `panel_axis_series_match: strong | partial | no`; `behavior_match: consistent | contradictory_after_debugging | not_comparable` is a diagnostic and not a forced agreement test.

An instruction-led run can have `protocol_lock_check.pass: true` and an empty `unresolved_fidelity_gaps` list when it faithfully executes its instruction-derived method, while `protocol_coverage_pass` remains false because no verified public-paper reproduction is claimed. Keep out-of-scope background-source limitations in a separate field such as `source_reproduction_limitations`; do not hide applicable core protocol gaps there.

The validator checks ID coverage, statuses, referenced paths, actual artifact presence, and consistency between per-item checks and the overall verdict. It does not validate scientific correctness, independently parse the raw instruction, or inspect figures. A structurally valid incomplete verdict is still incomplete. A passed structural check cannot establish research success.
