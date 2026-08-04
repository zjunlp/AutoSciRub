---
name: targeted-revision
description: Perform one AutoSciRub targeted revision round using failed executable-rubric criteria and criterion-level verification feedback. Use when Codex needs to update a research artifact by adding missing experiments, comparisons, evidence, analysis, figures, tables, or report text while preserving supported claims and recording a structured revision plan and change summary.
---

# Targeted Revision

## Purpose

Use failed criteria and diagnoses to revise the current artifact once. This implements `pi_rev(A_i^{(t)}, Delta_i^{(t)}, E_i | R_i)` from AutoSciRub.

This skill performs one bounded revision round. Run verification again only when the user or controller requests it.

## Inputs

Read:

1. `.autoscirub/executable_rubric.json`
2. `.autoscirub/verification_report.json` or the requested round-specific verification file
3. current report and supporting artifacts
4. task-visible data/code/tools needed to address gaps

## Output

For revision round `N`, write:

```text
.autoscirub/revisions/round-NNN/revision_plan.json
.autoscirub/revisions/round-NNN/change_summary.json
```

Use this revision-plan shape:

```json
{
  "schema_version": "1.0",
  "round": 1,
  "targets": [
    {
      "criterion_id": "C1",
      "gap": "...",
      "planned_actions": ["..."],
      "expected_artifacts": ["..."],
      "risk_or_dependency": "..."
    }
  ]
}
```

Use this change-summary shape:

```json
{
  "schema_version": "1.0",
  "round": 1,
  "changes": [
    {
      "criterion_id": "C1",
      "actions_completed": ["..."],
      "artifacts_changed": ["relative/path"],
      "remaining_gap": "none or specific limitation"
    }
  ]
}
```

## Procedure

1. Select failed criteria from the verification report, prioritizing high-priority evidence gaps.
2. Convert each gap into concrete actions: run missing analysis, add comparison, regenerate artifact, strengthen explanation, or remove unsupported claim.
3. Update code, results, figures, tables, and report text only as needed to address the failed criteria.
4. Preserve existing supported results and claims unless the new evidence contradicts them.
5. Record the plan before substantive changes when practical, then record the final change summary.

## Rules

- Perform exactly one revision round per invocation.
- Do not broaden the task beyond failed criteria unless a dependency is necessary to satisfy them.
- Do not fabricate results, labels, baselines, or references.
- If a requested fix is infeasible with available data, document the limitation and revise the report to avoid unsupported claims.
- Prefer adding missing evidence over cosmetic report edits.
