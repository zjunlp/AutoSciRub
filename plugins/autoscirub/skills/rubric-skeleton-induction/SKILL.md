---
name: rubric-skeleton-induction
description: Induce an instruction-derived scientific goal skeleton from a research task before reading literature, web sources, data details, code, or prior results. Use at the start of AutoSciRub when Codex needs atomic, traceable goals that state what the task should address without prescribing methods or metrics.
---

# Rubric Skeleton Induction

## Purpose

Transform an underspecified research instruction into a compact set of atomic scientific goals. This implements `phi_inst(x_i)` from AutoSciRub.

At this stage, define what the task should address. Do not decide how to prove it.

## Inputs

Use only the research instruction from the user or a user-specified instruction file. If no explicit file is provided, inspect obvious project-level instruction files only when present.

Do not read literature, web sources, data schemas, prior outputs, report drafts, hidden benchmark files, target papers, or detailed code.

## Output

Write `.autoscirub/rubric_skeleton.json` unless another state directory is configured.

Use this shape:

```json
{
  "schema_version": "1.0",
  "task_id": "optional-stable-id",
  "source": "instruction",
  "goals": [
    {
      "goal_id": "G1",
      "title": "Short goal title",
      "requirement": "One concrete scientific requirement implied by the instruction.",
      "instruction_evidence": ["Short quote or paraphrase from the instruction"]
    }
  ]
}
```

## Procedure

1. Extract the main scientific objectives, comparisons, analyses, and interpretation needs from the instruction.
2. Split compound requirements into atomic goals only when separate evidence will be needed.
3. Assign stable goal ids `G1`, `G2`, ... in task-logical order.
4. Preserve traceability by recording the instruction phrase or paraphrase that supports each goal.
5. Keep the skeleton small enough to guide execution, usually 3 to 7 goals.

## Rules

- Keep goals literal, task-oriented, and non-overlapping.
- Do not add specific methods, metrics, baselines, statistical tests, plots, expected results, or paper-specific claims.
- Do not add a goal unless it is supported by the instruction.
- Keep goals broad enough for later literature grounding and criterion synthesis.
- If the instruction is ambiguous, record the conservative interpretation rather than expanding the task scope.
