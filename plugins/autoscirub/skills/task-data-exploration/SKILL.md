---
name: task-data-exploration
description: Build a lightweight task-visible data and resource profile for AutoSciRub. Use after rubric skeleton and literature grounding when Codex needs to inspect available files, datasets, code, schemas, units, labels, tools, constraints, and goal feasibility before synthesizing executable criteria.
---

# Task-Data Exploration

## Purpose

Profile the task-visible environment without running full experiments. This implements `phi_data(E_i)` from AutoSciRub.

The profile determines which literature-suggested analyses are feasible with the current files, tools, labels, and compute context.

## Inputs

Read:

1. `.autoscirub/rubric_skeleton.json`
2. `.autoscirub/literature_grounding.json`
3. task instruction and optional config/profile
4. visible project files, datasets, code, metadata, and tool documentation

Respect exclusions from the user or task harness. Do not inspect hidden answers, target studies, private grading files, or files outside the task-visible environment.

## Inspection Procedure

Use lightweight inspection first:

- list relevant files, formats, and sizes
- inspect schemas, dimensions, columns, units, coordinates, labels, timestamps, conditions, model names, scenario fields, and identifiers
- sample small previews when safe
- identify joins, alignment keys, cross-source relations, and missing values
- identify available code utilities and required command interfaces
- record dependency risks without choosing a hard-coded environment

Avoid full model training, expensive simulation, final figure generation, or report writing in this step.

## Output

Write `.autoscirub/task_data_profile.json`:

```json
{
  "schema_version": "1.0",
  "files": [
    {
      "path": "relative/path",
      "format": "csv | json | hdf5 | image | text | code | other",
      "size_or_shape": "...",
      "key_fields": ["..."],
      "role": "input | label | reference | metadata | geometry | time_series | model_output | code | other",
      "notes": "..."
    }
  ],
  "datasets": [
    {
      "name": "...",
      "paths": ["..."],
      "entities": ["..."],
      "measurements": ["..."],
      "labels_or_targets": ["..."],
      "constraints": ["..."]
    }
  ],
  "relationships": ["join, alignment, temporal, spatial, or hierarchy relation"],
  "constraints": ["missing labels, limited samples, compute limits, unavailable reference values"],
  "goal_support": [
    {
      "goal_id": "G1",
      "supporting_files": ["..."],
      "feasible_analyses": ["..."],
      "unsupported_requirements": ["..."],
      "notes": "..."
    }
  ],
  "dependency_notes": ["libraries or external tools that may be needed, without activation commands"]
}
```

## Rules

- Keep paths relative to the task root when possible.
- Do not write virtual environment names, activation commands, or machine-specific absolute paths.
- Do not invent labels, ground truth, coordinates, units, or reference values.
- If a literature-suggested analysis is infeasible, explain the exact missing data or tool.
- Prefer direct task evidence; identify surrogate analyses only when they are defensible from available data.
