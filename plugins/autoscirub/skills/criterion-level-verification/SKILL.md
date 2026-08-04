---
name: criterion-level-verification
description: Verify a scientific report and supporting artifacts against an AutoSciRub executable rubric criterion by criterion. Use after execution has produced a report, code, results, tables, figures, or other artifacts, when Codex needs strict satisfaction labels, evidence found, evidence gaps, and required actions for targeted revision.
---

# Criterion-Level Verification

## Purpose

Check whether the current research artifact satisfies each executable-rubric criterion. This implements `Verify(rho_{i,j}, A_i^{(t)})` from AutoSciRub.

Verification diagnoses omissions; it does not edit the report or run a revision.

## Inputs

Read:

1. `.autoscirub/executable_rubric.json`
2. current report or generated artifact specified by the user
3. supporting code, results, tables, figures, logs, and analysis files as needed
4. optional prior verification report when comparing rounds

Do not inspect hidden benchmark answers, target reports, private grading checklists, or files excluded by a profile.

## Output

Write `.autoscirub/verification_report.json` or a round-specific file under `.autoscirub/revisions/round-XXX/verification.json`:

```json
{
  "schema_version": "1.0",
  "round": 1,
  "all_satisfied": false,
  "criteria": [
    {
      "criterion_id": "C1",
      "satisfied": false,
      "evidence_found": ["report section, figure, table, code path, result file, or quoted result"],
      "evidence_gap": "Specific missing or insufficient evidence.",
      "required_actions": ["action needed to satisfy the criterion"],
      "artifact_references": ["relative/path or report anchor"]
    }
  ],
  "summary": {
    "passed": 0,
    "failed": 0,
    "highest_priority_gaps": ["..."]
  }
}
```

## Verification Rules

- Check each criterion independently before judging the overall artifact.
- Mark a criterion satisfied only when the required analysis and supporting evidence are both present.
- Treat literature-only statements as insufficient when the criterion requires task-generated evidence.
- Check that conclusions are supported by artifacts, not merely asserted.
- Check that figures and tables have interpretable captions or report descriptions when the rubric expects them.
- Name the concrete missing experiment, comparison, metric, artifact, or explanation.
- Use stable criterion ids from the executable rubric; do not renumber during verification.

## Pass Standard

Set `all_satisfied` to true only when every high-priority and required criterion is satisfied, and any medium/low unsatisfied criteria are explicitly justified by the rubric or user scope.
