# MinerU API Reference

Source: https://mineru.net/apiManage/docs

## Mode Comparison

Standard API:

- Requires `Authorization: Bearer <token>`.
- Endpoints: `POST /api/v4/extract/task`, `POST /api/v4/file-urls/batch`, `GET /api/v4/extract/task/{task_id}`, `GET /api/v4/extract-results/batch/{batch_id}`.
- Models: `pipeline`, `vlm` (recommended), `MinerU-HTML`.
- Limits: 200 MB and 200 pages.
- Output: zip archive containing Markdown and JSON; `full.md` is the Markdown result.

Agent lightweight API:

- No token; IP-rate-limited.
- Endpoints: `POST /api/v1/agent/parse/url`, `POST /api/v1/agent/parse/file`, `GET /api/v1/agent/parse/{task_id}`.
- Fixed lightweight pipeline model.
- Limits: 10 MB and 20 pages.
- Output: `markdown_url` pointing to `full.md`.

## Standard API Parameters

Common JSON parameters:

- `model_version`: `vlm` by default for scientific PDFs.
- `language`: default `ch`; use `en` for English-only papers.
- `enable_table`: default true.
- `enable_formula`: default true.
- `is_ocr`: default false.
- `page_ranges`: standard API page selection, for example `1-10` or `2,4-6`.
- `extra_formats`: optional `docx`, `html`, `latex`; Markdown and JSON are default.

Local file standard flow:

1. `POST https://mineru.net/api/v4/file-urls/batch` with `{"files":[{"name":"paper.pdf","data_id":"paper.pdf"}],"model_version":"vlm"}`.
2. Upload bytes with `PUT <file_urls[0]>`; do not set `Content-Type`.
3. Poll `GET https://mineru.net/api/v4/extract-results/batch/{batch_id}`.
4. When `extract_result[0].state == "done"`, download `full_zip_url`.
5. Extract `full.md` from the zip.

URL standard flow:

1. `POST https://mineru.net/api/v4/extract/task` with `{"url":"...","model_version":"vlm"}`.
2. Poll `GET https://mineru.net/api/v4/extract/task/{task_id}`.
3. When `state == "done"`, download `full_zip_url`.
4. Extract `full.md`.

## Agent Lightweight API Parameters

Common JSON parameters:

- `language`: default `ch`; use `en` for English-only PDFs.
- `enable_table`: default true.
- `enable_formula`: default true.
- `is_ocr`: default false.
- `page_range`: lightweight API page selection, for example `1-10`.

Local file agent flow:

1. `POST https://mineru.net/api/v1/agent/parse/file` with `{"file_name":"paper.pdf"}` plus optional parameters.
2. Upload bytes with `PUT data.file_url`.
3. Poll `GET https://mineru.net/api/v1/agent/parse/{task_id}`.
4. When `state == "done"`, download `markdown_url`.

URL agent flow:

1. `POST https://mineru.net/api/v1/agent/parse/url` with `{"url":"..."}` plus optional parameters.
2. Poll `GET https://mineru.net/api/v1/agent/parse/{task_id}`.
3. When `state == "done"`, download `markdown_url`.

## Failure Handling

- Standard token errors include `A0202` and `A0211`; verify the bearer token or replace it.
- Standard file failures include oversize, too many pages, unsupported format, queue full, and parse failure.
- Agent errors include `-30001` for files over 10 MB, `-30003` for page-count overflow, and `429` for rate limiting.
- If lightweight parsing fails due to size or pages, retry with `MINERU_API_TOKEN` and `--mode standard`, or use `--page-range` for the first pages needed.
