---
name: scientific-literature-grounding
description: Ground an AutoSciRub rubric skeleton in scientific literature and authoritative documentation. Use after rubric_skeleton.json exists when a research agent needs goal-centered methods, protocols, metrics, baselines, controls, robustness checks, and evidence forms from task-visible papers, public literature, datasets, benchmarks, repositories, or documentation.
---

# Scientific Literature Grounding

## Purpose

Map each induced scientific goal to established scientific practice. This implements `phi_lit(g_{i,k}; L_i)` from AutoSciRub.

The output should help decide what evidence is scientifically appropriate. It is not a literature review for the final report.

All `.autoscirub/` paths below refer to the state directory resolved by the controller. When invoked alone, use the user’s override, then `AUTOSCIRUB_STATE_DIR`, then project config `state_dir`, then `.autoscirub/`.

## Inputs

Read:

1. `.autoscirub/rubric_skeleton.json`
2. task instruction if needed for context
3. `.autoscirub/config.yaml`, user-provided config, or `config/sources.example.yaml` when available
4. task-visible related literature or converted Markdown
5. normalized retrieval results from `$scientific-literature-grounding/scripts/retrieve_literature.py`
6. public web/literature sources through the active agent harness when useful
7. optional profile constraints such as hidden target-paper blocklists or forbidden paths

If PDFs are important and Markdown is unavailable, use an available PDF-to-Markdown utility before relying on lossy PDF extraction.

## Retrieval Script

Resolve `scripts/retrieve_literature.py` relative to this installed skill's directory, using the location supplied by the active agent. Do not guess a `codex skill path` command. Run from the research project, or pass `--project`.

For users working from the AutoSciRub checkout, the short entry point is:

```bash
python scripts/autoscirub.py retrieve --project /path/to/project --query "research question"
```

For an installed skill, run its resolved script path with `--goals` pointing to the rubric skeleton. Omit `--config` to read project `.autoscirub/config.yaml` automatically. Omit `--out` to write the source index under the resolved state directory. Pass `--validate-config` for a local check. If dependencies are missing, follow the script's installation hint in the user's active Python environment.

The script handles arXiv, OpenAlex, Semantic Scholar, Tavily, and local document indexing. `web` is an explicit handoff to the agent's native search, not a built-in provider. Provider credentials come only from the environment variables named in config.

- Local documents: configure `retrieval.local_literature.paths`; paths are project-relative. Apply `excluded_paths` before scanning or reading any document. The source index contains paths/metadata, not full-text analysis or a relevance guarantee.
- Local-only tasks: enable only `local_literature`; do not call web or PDF upload services. Existing Markdown can be read directly.
- Remote queries: show progress and inspect `provider_results`. `empty` means a completed query found no usable result; `failed` means an error; `skipped` states why the source was unavailable.
- A partially successful retrieval can support grounding if the available evidence is sufficient. Describe the missing coverage.
- An all-failed/unavailable run exits with code 3 and writes `literature_sources.failure.json`, preserving the old index. Never silently treat an old index as results from the failed run.
- The first core sources are provisional candidates. Read and assess relevance and goal coverage before using them as scientific support.

Running the helper is optional. Native search or direct reading may be more suitable, but preserve the same config exclusions, source provenance, and user network constraints.

## Search Rules

- Search broad concepts, method families, metrics, benchmark names, protocol names, dataset names, and official documentation.
- Prefer papers, preprints, official dataset pages, benchmark docs, method repositories, and software documentation.
- Preserve distinctive methods, settings, or phrases explicitly provided by the user when they improve search relevance. Apply benchmark-specific restrictions only when an explicit profile requires them.
- Apply any blocklist or exclusion rule supplied by the task harness before reading full text.
- Use enough relevant sources to support the task, without a minimum quota. Do not expand a simple local task into a broad literature survey.
- Use `.autoscirub/literature_sources.json` as the normalized source index when the retrieval script has been run.

## Output

Write `.autoscirub/literature_grounding.json`:

```json
{
  "schema_version": "1.0",
  "sources": [
    {
      "source_id": "S1",
      "title": "...",
      "url_or_path": "...",
      "source_type": "paper | preprint | documentation | dataset | benchmark | repository | other",
      "used_for_goal_ids": ["G1"]
    }
  ],
  "goals": [
    {
      "goal_id": "G1",
      "queries": ["..."],
      "source_ids": ["S1"],
      "methods": ["method and why it matters"],
      "metrics": ["metric or value and how it is used"],
      "baselines": ["baseline or comparison axis"],
      "controls": ["control, negative case, or sanity check"],
      "robustness_checks": ["sensitivity or ablation"],
      "evidence_forms": ["figure, table, number, file, or textual analysis and what it must show"],
      "feasibility_questions": ["data/tool question to resolve during task-data exploration"]
    }
  ]
}
```

## Quality Bar

- Organize findings by goal, not by paper.
- Explain why each method, metric, baseline, or artifact matters.
- Prefer execution-driving details over background summaries.
- Mark uncertain or conflicting literature guidance explicitly.
- Do not treat literature claims as evidence for the current task unless reproduced using task-visible data.
