---
name: scientific-literature-grounding
description: Ground an AutoSciRub rubric skeleton in scientific literature and authoritative documentation. Use after rubric_skeleton.json exists when Codex needs goal-centered methods, protocols, metrics, baselines, controls, robustness checks, and evidence forms from task-visible papers, public literature, datasets, benchmarks, repositories, or documentation.
---

# Scientific Literature Grounding

## Purpose

Map each induced scientific goal to established scientific practice. This implements `phi_lit(g_{i,k}; L_i)` from AutoSciRub.

The output should help decide what evidence is scientifically appropriate. It is not a literature review for the final report.

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

A bundled script is available at `$scientific-literature-grounding/scripts/retrieve_literature.py`. Use it when you want a single normalized source index instead of assembling results manually:

```bash
python "$(codex skill path scientific-literature-grounding 2>/dev/null || echo .)"/scripts/retrieve_literature.py \
  --config .autoscirub/config.yaml \
  --goals .autoscirub/rubric_skeleton.json \
  --out .autoscirub/literature_sources.json
```

Running the script is optional. You may also call the providers directly, use the agent harness's native web search, or mix both approaches.

If `.autoscirub/config.yaml` is absent, copy or adapt `config/sources.example.yaml` from the AutoSciRub repository. The script reads API keys only from the environment variables named in the config, such as `SEMANTIC_SCHOLAR_API_KEY`, `TAVILY_API_KEY`, and `OPENALEX_EMAIL`.

The script supports arXiv, OpenAlex, Semantic Scholar, and Tavily. `web` and `local_literature` are handled by the active agent harness and task-visible files.

## Per-Provider Reference

Use these details to choose providers and call them correctly, whether you use the bundled script or call the APIs yourself. Normalize any manually-retrieved results into the same fields used by `literature_sources.json`.

### arXiv

- No API key required.
- Endpoint: `http://export.arxiv.org/api/query`
- Required parameters: `search_query`, `start`, `max_results`, `sortBy=relevance`, `sortOrder=descending`
- Response format: Atom XML; each `<entry>` contains `title`, `summary`, `id` (abs page), `published`, and authors.
- Use broad concept queries rather than long phrases.
- Script output maps arXiv entries to `source_type: preprint` with an `arxiv` provider tag.

### OpenAlex

- No API key required. Set `OPENALEX_EMAIL` (or the configured `email_env`) to enter the polite pool and get more reliable rate limits.
- Endpoint: `https://api.openalex.org/works`
- Required parameters: `search`, `per-page`; optionally `mailto=<email>` for the polite pool.
- Response format: JSON with `results[]`. Each work has `title`, `abstract_inverted_index`, `authorships`, `doi`, `publication_date`, `cited_by_count`, and `open_access.oa_url`.
- Reconstruct abstract text from `abstract_inverted_index` if needed.
- Script output maps OpenAlex works to `source_type: paper` with an `openalex` provider tag and a `citations` count.

### Semantic Scholar

- API key optional but recommended. Without a key, expect strict rate limits and frequent HTTP 429.
- Environment variable: `SEMANTIC_SCHOLAR_API_KEY` (or configured `api_key_env`).
- Endpoint: `https://api.semanticscholar.org/graph/v1/paper/search`
- Required parameters: `query`, `limit`, `fields`
- Useful `fields`: `title,abstract,authors,url,externalIds,year,citationCount,publicationTypes`
- Request headers without key: `Accept: application/json`
- Request headers with key: `x-api-key: <KEY>`
- Response format: JSON with `data[]`; each paper has `title`, `abstract`, `authors`, `url`, `year`, `citationCount`.
- Script output maps Semantic Scholar papers to `source_type: paper` with a `semantic_scholar` provider tag.

### Tavily

- API key required. Requests without a valid key return HTTP 401.
- Environment variable: `TAVILY_API_KEY` (or configured `api_key_env`).
- Endpoint: `https://api.tavily.com/search`
- Method: `POST`
- Required body fields: `api_key`, `query`, `search_depth`, `max_results`
- Typical values: `search_depth=basic`, `max_results` up to 20 for lightweight use.
- Response format: JSON with `results[]`; each result has `title`, `url`, `content`, `score`.
- Script output maps Tavily results to `source_type: web` with a `tavily` provider tag.

## Search Rules

- Search broad concepts, method families, metrics, benchmark names, protocol names, dataset names, and official documentation.
- Prefer papers, preprints, official dataset pages, benchmark docs, method repositories, and software documentation.
- Avoid long exact instruction spans, task identifiers, task-specific filenames, and hidden-target clues.
- Apply any blocklist or exclusion rule supplied by the task harness before reading full text.
- Keep 5 to 7 core sources when enough good sources exist; add targeted docs only when needed.
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
