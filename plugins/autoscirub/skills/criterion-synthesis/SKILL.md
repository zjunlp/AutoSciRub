---
name: criterion-synthesis
description: Synthesize a task-specific executable scientific rubric from an instruction-derived skeleton, literature grounding, and task-data profile. Use in AutoSciRub when Codex needs criteria with linked goals, data sources, required analyses, metrics, comparisons, expected artifacts, provenance, and satisfaction conditions.
---

# Criterion Synthesis

## Purpose

Combine instruction goals, scientific practice, and task-data feasibility into an executable rubric. This implements `phi_syn(G_i, K_i, P_i)` from AutoSciRub.

The rubric is the contract for execution, verification, and revision.

## Inputs

Read:

1. `.autoscirub/rubric_skeleton.json`
2. `.autoscirub/literature_grounding.json`
3. `.autoscirub/task_data_profile.json`
4. optional task config/profile

## Output

Write `.autoscirub/executable_rubric.json`:

```json
{
  "schema_version": "1.0",
  "goals": [
    {
      "goal_id": "G1",
      "title": "...",
      "requirement": "..."
    }
  ],
  "criteria": [
    {
      "criterion_id": "C1",
      "goal_ids": ["G1"],
      "requirement": "Concrete requirement to satisfy.",
      "data_sources": ["relative/path or dataset field"],
      "required_analysis": ["experiment, computation, comparison, proof step, or diagnostic"],
      "metrics": ["metric, statistic, threshold, or qualitative check"],
      "comparisons": ["baseline, control, condition, region, time, model, or ablation"],
      "expected_artifacts": [
        {
          "type": "figure | table | number | file | code | text_analysis",
          "name": "semantic artifact name",
          "expected_path": "optional relative path",
          "must_show": "what the artifact must demonstrate"
        }
      ],
      "satisfaction_condition": "Observable condition for marking the criterion satisfied.",
      "priority": "high | medium | low",
      "provenance": {
        "instruction": ["goal or instruction evidence"],
        "literature": ["source id or summarized guidance"],
        "data_profile": ["supporting files or feasibility notes"]
      }
    }
  ],
  "claims_to_avoid": ["unsupported claim pattern"]
}
```

## Procedure

1. Preserve every skeleton goal unless task-visible data proves it impossible.
2. Select feasible analyses that best satisfy each goal using literature-grounded practice.
3. Convert each requirement into a criterion with observable evidence and a satisfaction condition.
4. Link each criterion to goals, data sources, artifacts, and provenance.
5. Record unsupported or risky claims that the execution agent should avoid.

## Rules

- Prefer criteria that can be checked against code, results, figures, tables, files, or report text.
- Use direct task data when available; only allow surrogate analyses when the data profile justifies them.
- Avoid generic criteria such as "analyze thoroughly" or "discuss results".
- Do not require unavailable labels, tools, target answers, or external private data.
- Keep the rubric compact enough to execute, usually 6 to 15 criteria.
