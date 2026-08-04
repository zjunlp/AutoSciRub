---
name: mineru-pdf-to-markdown
description: Convert PDFs and paper-like documents into Markdown with MinerU before reading or analyzing them. Use when AutoSciRub or another scientific agent needs to inspect local or remote PDFs, equations, tables, or scanned papers where direct PDF text extraction would be lossy; supports MinerU Agent lightweight API without a token and MinerU standard API with MINERU_API_TOKEN.
---

# MinerU PDF to Markdown

## Overview

Use this optional utility before detailed reading of scientific PDFs. Convert relevant PDFs to Markdown, then read the Markdown during literature grounding or document analysis.

The bundled script handles MinerU submission, file upload, polling, result download, zip extraction, caching, and a JSONL parse log.

## Quick Start

From the plugin skill directory or with the script path resolved by the agent:

```bash
python scripts/mineru_pdf_to_markdown.py related_work/*.pdf
```

Convert one PDF and force the standard high-accuracy API:

```bash
MINERU_API_TOKEN="$MINERU_API_TOKEN" python scripts/mineru_pdf_to_markdown.py paper.pdf --mode standard --model-version vlm
```

Convert only selected pages:

```bash
python scripts/mineru_pdf_to_markdown.py paper.pdf --page-range 1-10
```

Use `--output-dir` to choose a project-relative destination. If omitted, the script defaults to `pdf_markdown/` under the current working directory.

## Workflow

1. Identify PDFs likely to influence task goals, methods, metrics, datasets, protocols, or evidence forms.
2. Run the converter before detailed reading.
3. Read generated `*.md` files instead of relying on raw PDF extraction.
4. Cite local Markdown paths in working notes when a converted paper informs rubric induction, grounding, or criterion synthesis.
5. Reuse cached Markdown unless the PDF changed or the prior parse is clearly poor; use `--force` to refresh.

## API Selection

Use `--mode auto` by default:

- If `MINERU_API_TOKEN` is set, the script uses MinerU standard API with `vlm` by default.
- If no token is set, the script uses MinerU Agent lightweight API.
- For local files larger than 10 MB, prefer the standard API.
- For long papers with the lightweight API, pass `--page-range`.

Read `references/mineru_api.md` when changing API parameters, debugging MinerU failures, or deciding between standard and lightweight modes.

## Output Contract

For each input, the script writes:

- `<output-dir>/<safe-input-name>.md`: Markdown content for reading.
- `<output-dir>/<safe-input-name>.meta.json`: task id, mode, source, result URLs, and status.
- `<output-dir>/_mineru_parse_log.jsonl`: append-only conversion log.
- `<output-dir>/_zip/` and `<output-dir>/_extracted/` for standard API zip results.

Use converted Markdown as literature or document context, not as a replacement for task-generated experimental evidence.
