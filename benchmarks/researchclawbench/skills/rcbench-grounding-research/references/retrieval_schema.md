# Retrieval interface

Use this reference when constructing query plans, invoking the retriever, or analyzing traces. Effort and providers are configured in `.rcbench/profile.yaml`; the bundled legacy source configuration is only a reference for provider options.

## Query-plan input

Prefer a JSON plan to repeated `--query` arguments because it preserves provenance:

```json
{
  "queries": [
    {
      "query_id": "q01",
      "stage": "initial",
      "query": "distinctive method dataset metric",
      "target_signal": "The missing public evidence this query can recover",
      "key_terms": ["method", "dataset", "metric"],
      "priority": 1,
      "parent_query_id": null
    }
  ]
}
```

- Use stable unique query IDs. Stages are `initial` and `followup`; `priority` ranks candidates for ordinary provider budgets.
- Initial and followup counts use `workflow.max_initial_queries` and `workflow.max_followup_queries`. The default profile allows 3 initial and 1 followup; these are maxima, not required counts. `retrieval.limits.max_queries_per_task` is the combined cap. Adjust related profile limits together before starting a run.
- A followup addresses an identified missing signal. Prefer a documented citation pivot when available; otherwise target missing scientific evidence, public code, or supplements explicitly. Record `parent_query_id` and a compact `target_signal`; never invent a citation or record hidden reasoning.
- SciAtlas selects queries mechanically using exact phrases, named methods, acronyms, numbers, and key terms, within its configured budget. Provider budgets are cumulative across `--resume`, including failed attempts; resuming does not silently repeat them.
- Reuse adequate text. New full-text recovery shares `workflow.max_full_texts`; retrieval candidates and full-text conversions are different operations.

## Portable commands

Resolve `RCBENCH_SKILLS` from the actual installed parent of the loaded skill directory and `RCBENCH_PYTHON` from a user-prepared profile environment, as described by the controller and adaptation README. Credentials come from configured environment variables; do not source a developer's private credential file or store secrets in task artifacts.

From the task workspace:

```bash
"$RCBENCH_PYTHON" "$RCBENCH_SKILLS/rcbench-grounding-research/scripts/retrieve_literature.py" \
  --config .rcbench/profile.yaml \
  --workspace . \
  --query-plan outputs/retrieval_query_plan.json \
  --task-id TASK \
  --out outputs/literature_candidates.json \
  --trace-out outputs/retrieval_trace.json
```

Replace `TASK` with the task identifier. Relative input/output paths are resolved against `--workspace`; the explicit configuration path is resolved from the invocation directory. After adding an evidence-backed followup to the plan, repeat the command with `--resume`. Completed provider/query requests are preserved; new queries use remaining cumulative provider capacity.

After writing `outputs/grounding_research.json`, annotate the trace without rerunning retrieval:

```bash
"$RCBENCH_PYTHON" "$RCBENCH_SKILLS/rcbench-grounding-research/scripts/annotate_retrieval_trace.py" \
  --trace outputs/retrieval_trace.json \
  --grounding outputs/grounding_research.json
```

## Outputs and failures

`outputs/literature_candidates.json` contains normalized, deduplicated candidates ordered by reciprocal-rank fusion. The fused order guides triage, not paper identity or scientific relevance.

`outputs/retrieval_trace.json` preserves query plans, provider attempts and safe parameters, elapsed time/status/error, returned provider ranks/scores, canonical identifiers, cross-provider matches, and per-query counts. SciAtlas attempts additionally record its discriminative query selection. Never compare raw scores across providers or include credentials/authorization headers in artifacts.

`possible_hit` and `final_candidate_hit` begin as null. The annotator adds labels from the agent's grounding contract for later retrieval analysis; these are not independently verified target matches.

Missing optional credentials skip that provider; other configured sources continue. Partial provider failures do not discard successful evidence. If every new attempted request fails, inspect the failure diagnostics; the retriever writes `*.failed.json` instead of replacing earlier successful candidates/traces and exits nonzero. Do not treat that failure as a successful empty search or overwrite prior evidence. Record exhausted retrieval or full-text budgets as limitations and retain all unresolved task obligations.
