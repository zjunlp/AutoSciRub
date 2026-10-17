---
name: rcbench-mineru-pdf-to-markdown
description: Recover readable scientific PDF content with MinerU for the ResearchClawBench adaptation when relevant full text is missing or inadequate. Preserve equations and tables, cache derived text outside supplied inputs, and reuse reliable existing text.
---

# ResearchClawBench MinerU Recovery

Use for relevant scientific PDFs whose available text is inadequate. Inspect figures directly when visual semantics matter; Markdown cannot replace viewing a scientific figure. Do not convert every PDF automatically.

Read `.rcbench/profile.yaml` and the adaptation README for prepared Python environments and optional credentials. Resolve `RCBENCH_SKILLS` from the actual installed parent of this skill directory and `RCBENCH_PYTHON` from a prepared profile environment. From the task workspace:

```bash
"$RCBENCH_PYTHON" "$RCBENCH_SKILLS/rcbench-mineru-pdf-to-markdown/scripts/mineru_pdf_to_markdown.py" \
  "related_work/paper.pdf" \
  --config .rcbench/profile.yaml \
  --workspace . \
  --output-dir artifacts/literature/pdf_markdown
```

Use `--page-range 1-10` for selected pages. New full-text acquisitions/conversions share `workflow.max_full_texts` across grounding; do not restart that budget per invocation. Reuse cached Markdown unless the PDF changed or parsing was inadequate; use `--force` only to refresh such a parse.

`--mode auto` selects the standard API when `MINERU_API_TOKEN` is available and the Agent API otherwise. Use `--mode standard --model-version vlm` for explicit standard parsing. Read [references/mineru_api.md](references/mineru_api.md) for parameters and failure handling. Remote conversion sends the selected document to MinerU; use it within task authorization and data constraints.

Under `artifacts/literature/pdf_markdown/`, the script writes `<safe-input-name>.md`, `<safe-input-name>.meta.json`, `_mineru_parse_log.jsonl`, and standard API archives/assets in `_zip/` and `_extracted/`.

Keep supplied `related_work/` and `data/` unchanged. Cite original public sources in reports and retain parse provenance. Never access hidden checklists, `target_study` files, judge feedback, or other tasks' runs, even if reachable in the workspace. If conversion fails, retain the failure, use adequate permitted text if available, and record unresolved evidence gaps.
