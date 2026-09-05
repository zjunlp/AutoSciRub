---
name: autoscirub
description: Coordinate the full AutoSciRub workflow for autonomous scientific research tasks. Use when a user wants to turn an underspecified research instruction into an executable rubric, guide research execution, verify a report criterion by criterion, and run targeted revision rounds across Codex, Claude Code, OpenClaw, or another agent harness.
---

# AutoSciRub

## Purpose

Use this skill as the top-level controller for the AutoSciRub method:

1. Rubric Skeleton Induction
2. Scientific Literature Grounding
3. Task-Data Exploration
4. Criterion Synthesis
5. Rubric-guided execution by the current research agent
6. Criterion-Level Verification
7. Targeted Revision

AutoSciRub creates a task-specific executable rubric at inference time, then uses it as an execution and verification contract.

## State Contract

Use the current project as the task root. Resolve the state directory once: explicit user choice, then `AUTOSCIRUB_STATE_DIR`, then `state_dir` in project `.autoscirub/config.yaml`, then `.autoscirub/`. All relative paths are relative to the research project. Throughout this skill and its child skills, replace `.autoscirub/` output paths with that resolved directory.

Expected files:

```text
.autoscirub/
  run_manifest.json
  rubric_skeleton.json
  literature_sources.json       # when bundled retrieval is used
  literature_grounding.json
  task_data_profile.json
  executable_rubric.json
  verification_report.json
  revisions/
    round-001/
      verification.json
      revision_plan.json
      change_summary.json
```

Do not assume fixed paths such as `INSTRUCTIONS.md`, `data/`, `outputs/`, or `report/`. If those files exist, use them. Otherwise use the task text, user-specified paths, and discoverable project files.

## Inputs

Collect these inputs when available:

- research instruction from the user or an instruction file
- optional `.autoscirub/config.yaml` or user-provided config
- task-visible literature, data, code, tools, and prior artifacts
- optional benchmark profile that declares hidden-file exclusions, blocklists, or output conventions

Treat profiles as constraints injected by the harness, not as built-in assumptions.

## Workflow

0. Establish the user’s requested boundary (rubric only, verification only, or execution). Reuse valid artifacts for the same task; do not regenerate them just because the workflow starts here. At the start and end, write `run_manifest.json` with task summary, resolved state directory, requested boundary, current stage, status (`running`, `completed`, `blocked`, or `budget_exhausted`), revision limit, completed rounds, and artifact paths. Treat this as a progress record, not proof that outputs are valid.
1. Run `rubric-skeleton-induction` using only the instruction. Write `.autoscirub/rubric_skeleton.json`.
2. Run `scientific-literature-grounding` using the skeleton and task-visible literature/search. Write `.autoscirub/literature_grounding.json`.
3. Run `task-data-exploration` using lightweight inspection of visible data and tools. Write `.autoscirub/task_data_profile.json`.
4. Run `criterion-synthesis` to combine goals, literature grounding, and data feasibility. Write `.autoscirub/executable_rubric.json`.
5. Execute the research task against the executable rubric. Produce the report and supporting code/results in project-appropriate locations.
6. Run `criterion-level-verification` against the current artifact. Write `.autoscirub/verification_report.json` or a round-specific verification file.
7. For an authorized full workflow, use the user’s revision limit or `workflow.max_revision_rounds` (default 1). After each `targeted-revision` round, rerun verification on the changed artifacts. Stop when all criteria pass, the budget is exhausted, or remaining gaps need unavailable inputs. Standalone verification never authorizes revision.

## Execution Rules

- Keep the rubric explicit and evidence-oriented. Each criterion should be verifiable against artifacts.
- Use literature to design scientific evidence, not as a substitute for task-generated evidence.
- Use lightweight data exploration during induction; defer full experiments to execution.
- Do not invent labels, measurements, target values, hidden files, or unavailable resources.
- Do not hard-code virtual environments, dependency managers, API providers, model names, or machine paths.
- Use the user's active environment and agent-native tools unless the user provides a different setup.
- Tell the user which stage is running and where its results are saved. At handoff, name the report, evidence, failed criteria, and next actionable step.
- For a small task, keep goals and criteria correspondingly small; numerical size suggestions in child skills are not quotas.
- Stop after the requested boundary: induction only, execution only, verification only, or one revision round.

## Completion Criteria

For rubric-only work, completion is the requested rubric artifact. For verification-only work, completion is a truthful verification report, even if criteria fail. For full execution, report success only when all in-scope criteria pass; budget exhaustion or missing inputs must remain explicit and must not be relabelled as scientific success.
