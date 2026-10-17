---
name: rcbench-workflow-controller
description: Run the ResearchClawBench adaptation of AutoSciRub from instruction extraction through public-source grounding, faithful experiments, report verification, and evidence repair. Use for a complete benchmark task or an authorized continuation.
---

# AutoSciRub for ResearchClawBench

Preserve the scientific requirements and evidence-repair design of `skills-0901-r2`; environment and effort settings come from the workspace profile.

## Workspace and configuration

Read `INSTRUCTIONS.md` and the user-prepared `.rcbench/profile.yaml`. Follow the adaptation README for environment preparation; use `ENVIRONMENTS.md` as additional context when supplied. Select a configured Python environment and perform a small import precheck before experiments. Do not assume a particular virtual environment exists.

Resolve `RCBENCH_SKILLS` to the absolute parent of this loaded skill directory, using its actual installed location. Resolve siblings and scripts from there, never from the task working directory or a developer's checkout. Use `RCBENCH_PYTHON` for the selected executable. From the task workspace:

```bash
"$RCBENCH_PYTHON" "$RCBENCH_SKILLS/rcbench-workflow-controller/scripts/rcbench.py" config --workspace .
"$RCBENCH_PYTHON" "$RCBENCH_SKILLS/rcbench-workflow-controller/scripts/rcbench.py" doctor --workspace .
```

If the profile is absent, `init --workspace .` creates an editable template without replacing an existing profile. Choose available user-prepared interpreters and inspect missing prerequisites before execution. Do not modify unrelated environments. After the profile is prepared and before research begins, run `start --workspace .` to freeze `outputs/rcbench_run_manifest.json` with version, profile, and installed-skill hashes. An identical start is idempotent; a changed configuration or skill bundle requires a new run workspace or explicitly archived prior run. `init` does not freeze unfinished configuration.

Use task-visible inputs and public scientific sources. Never read hidden checklists, `target_study` material, judge feedback, or other tasks' runs, wherever located. Preserve supplied `data/` and `related_work/`; write derived literature to `artifacts/literature/`, results to `outputs/`, and the report to `report/report.md`. Place report figures under `report/images/` and embed their relative paths in the Markdown so the evaluator can see them.

## Plan and execute

1. Use `rcbench-instruction-rubric` to extract the raw instruction into `outputs/initial_rubric.json` before literature or data analysis.
2. Use `rcbench-grounding-research` to recover relevant public methods and results. Reuse reliable full text; use `rcbench-mineru-pdf-to-markdown` only for relevant missing or inadequate text. Preserve retrieval observability artifacts and write `outputs/grounding_research.json`.
3. Use `rcbench-experiments-design` to inspect supplied data and map every instruction requirement and relevant source result into `outputs/refined_rubric.json`. Read [references/contracts.md](references/contracts.md) for fields and statuses.
4. Reread the raw instruction and applicable source results. Check complete method, condition, baseline, metric, sample-setting, and figure/table coverage. Run:

   ```bash
   "$RCBENCH_PYTHON" "$RCBENCH_SKILLS/rcbench-workflow-controller/scripts/rcbench.py" check --workspace . --phase plan
   ```

5. Execute in dependency order. Pilot each core experiment and inspect its data and artifact before scaling. Preserve the distinguishing method, full comparison matrix, metric definitions, panels, axes/columns, units, and series. Cache reusable features and model outputs. Use the user's experiment runner when configured.
6. Write a concise scientific report centered on generated evidence. Trace measurements to result files; distinguish measurements, transparent reconstructions, and literature context.

An adjacent classifier, correlation, pooled curve, single case, partial baseline set, or convenient chart cannot replace a requested scientific comparison. A reconstruction counts as completion only if it preserves the required mechanism and scientific question. Otherwise retain the unresolved core gap. Never turn a difficult research task into a generic audit.

Expected trends and literature values are diagnostics. If results are opposite or implausible, check initialization, objective, split, normalization, units, metric/sign, and plotting transformations; rerun affected computations. Accept genuine contradictory findings after documenting these checks.

## Verify and repair

Use `rcbench-report-verifier` to independently re-enumerate obligations from the raw instruction and relevant public sources, visually inspect core artifacts, and write `outputs/report_rubric_check.json`. Independence concerns the evidence inventory; it does not imply a separate agent performed review.

For each permitted repair round, fix underlying evidence in order: wrong source/method, omitted task artifact, incomplete condition/baseline matrix, incorrect panel/axis/unit/series semantics, incorrect setting/metric, unsupported claim, then presentation. Rerun affected experiments and regenerate the actual report figure/table. An unrelated overview or extra ablation does not repair a missing core result. Reverify and run:

```bash
"$RCBENCH_PYTHON" "$RCBENCH_SKILLS/rcbench-workflow-controller/scripts/rcbench.py" check --workspace . --phase final
```

Report scientific validity, instruction completion, and source-protocol coverage separately. Source identification is a grounding diagnosis, not a universal success condition: a task without a source-reproduction requirement can finish from instruction-led evidence when no reliable match exists. An explicit reproduction requirement or an already applicable core source obligation remains unresolved until evidence closes it. Never change applicability or delete obligations merely to obtain a pass. Structural validation supplements scientific and visual review; it does not certify the science.

All effort limits come from `profile.workflow`: initial/followup queries, new full-text acquisitions, repair rounds, and report figures. Defaults are starting settings, not quotas or scientific completion criteria. Do not retrieve/plot to fill them or drop required comparisons when a limit is reached. Consolidate equivalent panels where appropriate and record unresolved work if configured resources are insufficient.
