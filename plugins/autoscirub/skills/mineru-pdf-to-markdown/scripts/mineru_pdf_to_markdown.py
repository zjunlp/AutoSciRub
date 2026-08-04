#!/usr/bin/env python3
"""Convert local or remote PDFs/documents to Markdown with MinerU APIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


BASE_URL = "https://mineru.net"
LIGHTWEIGHT_MAX_BYTES = 10 * 1024 * 1024
PENDING_STATES = {"waiting-file", "uploading", "pending", "running", "converting"}
DONE_STATE = "done"
FAILED_STATE = "failed"


class MinerUError(RuntimeError):
    pass


def is_url(value: str) -> bool:
    return urllib.parse.urlparse(value).scheme in {"http", "https"}


def safe_stem(source: str) -> str:
    if is_url(source):
        parsed = urllib.parse.urlparse(source)
        name = Path(parsed.path).name or parsed.netloc or "remote-document"
    else:
        name = Path(source).name
    stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", name)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return stem[:120] or hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_fingerprint(source: str) -> str:
    if is_url(source):
        return "url:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
    path = Path(source).resolve()
    return "file:" + file_sha256(path)


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    data = None
    req_headers = {"Accept": "*/*"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise MinerUError(f"HTTP {exc.code} from {url}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise MinerUError(f"Request failed for {url}: {exc}") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MinerUError(f"Non-JSON response from {url}: {raw[:500]}") from exc
    if result.get("code") not in (0, "0", None):
        raise MinerUError(f"MinerU API error from {url}: {result}")
    return result


def put_file(upload_url: str, path: Path, timeout: int = 300) -> None:
    data = path.read_bytes()
    req = urllib.request.Request(
        upload_url,
        data=data,
        headers={"Content-Type": "", "Content-Length": str(len(data))},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise MinerUError(f"Upload failed with HTTP {exc.code}: {body[:500]}") from exc
    if status not in (200, 201, 204):
        raise MinerUError(f"Upload failed with HTTP {status}")


def download_bytes(url: str, timeout: int = 300) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise MinerUError(f"Download failed with HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise MinerUError(f"Download failed for {url}: {exc}") from exc


def auth_headers(token: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


def common_payload(args: argparse.Namespace, *, standard: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "language": args.language,
        "enable_table": args.enable_table,
        "enable_formula": args.enable_formula,
        "is_ocr": args.ocr,
    }
    if standard:
        payload["model_version"] = args.model_version
        if args.page_range:
            payload["page_ranges"] = args.page_range
    else:
        if args.page_range:
            payload["page_range"] = args.page_range
    return payload


def poll_agent(task_id: str, timeout: int, interval: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    url = f"{BASE_URL}/api/v1/agent/parse/{task_id}"
    while time.time() < deadline:
        result = request_json("GET", url)
        data = result.get("data") or {}
        state = data.get("state")
        if state == DONE_STATE:
            return data
        if state == FAILED_STATE:
            raise MinerUError(f"Agent parse failed for task {task_id}: {data}")
        if state not in PENDING_STATES:
            raise MinerUError(f"Unexpected agent task state for {task_id}: {data}")
        time.sleep(interval)
    raise MinerUError(f"Timed out waiting for MinerU agent task {task_id}")


def poll_standard_task(task_id: str, token: str, timeout: int, interval: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    url = f"{BASE_URL}/api/v4/extract/task/{task_id}"
    headers = auth_headers(token)
    while time.time() < deadline:
        result = request_json("GET", url, headers=headers)
        data = result.get("data") or {}
        state = data.get("state")
        if state == DONE_STATE:
            return data
        if state == FAILED_STATE:
            raise MinerUError(f"Standard parse failed for task {task_id}: {data}")
        if state not in PENDING_STATES:
            raise MinerUError(f"Unexpected standard task state for {task_id}: {data}")
        time.sleep(interval)
    raise MinerUError(f"Timed out waiting for MinerU standard task {task_id}")


def poll_standard_batch(batch_id: str, token: str, timeout: int, interval: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    url = f"{BASE_URL}/api/v4/extract-results/batch/{batch_id}"
    headers = auth_headers(token)
    while time.time() < deadline:
        result = request_json("GET", url, headers=headers)
        data = result.get("data") or {}
        items = data.get("extract_result") or []
        if isinstance(items, dict):
            items = [items]
        if not items:
            time.sleep(interval)
            continue
        item = items[0]
        state = item.get("state")
        if state == DONE_STATE:
            return item
        if state == FAILED_STATE:
            raise MinerUError(f"Standard batch parse failed for batch {batch_id}: {item}")
        if state not in PENDING_STATES:
            raise MinerUError(f"Unexpected standard batch state for {batch_id}: {item}")
        time.sleep(interval)
    raise MinerUError(f"Timed out waiting for MinerU standard batch {batch_id}")


def extract_full_md(zip_bytes: bytes, zip_path: Path, extract_dir: Path) -> str:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(zip_bytes)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    candidates = sorted(extract_dir.rglob("full.md"))
    if not candidates:
        candidates = sorted(extract_dir.rglob("*.md"))
    if not candidates:
        raise MinerUError(f"No Markdown file found in MinerU zip {zip_path}")
    return candidates[0].read_text(encoding="utf-8", errors="replace")


def parse_agent(source: str, out_base: Path, args: argparse.Namespace) -> dict[str, Any]:
    payload = common_payload(args, standard=False)
    if is_url(source):
        payload["url"] = source
        payload.setdefault("file_name", Path(urllib.parse.urlparse(source).path).name)
        result = request_json("POST", f"{BASE_URL}/api/v1/agent/parse/url", payload)
    else:
        path = Path(source)
        if path.stat().st_size > LIGHTWEIGHT_MAX_BYTES:
            raise MinerUError("Local file exceeds lightweight API 10 MB limit; set MINERU_API_TOKEN and use --mode standard.")
        payload["file_name"] = path.name
        result = request_json("POST", f"{BASE_URL}/api/v1/agent/parse/file", payload)
        data = result.get("data") or {}
        upload_url = data.get("file_url")
        if not upload_url:
            raise MinerUError(f"MinerU agent did not return file_url: {result}")
        put_file(upload_url, path)
    task_id = (result.get("data") or {}).get("task_id")
    if not task_id:
        raise MinerUError(f"MinerU agent did not return task_id: {result}")
    final = poll_agent(task_id, args.timeout, args.interval)
    markdown_url = final.get("markdown_url")
    if not markdown_url:
        raise MinerUError(f"MinerU agent completed without markdown_url: {final}")
    markdown = download_bytes(markdown_url).decode("utf-8", errors="replace")
    md_path = out_base.with_suffix(".md")
    md_path.write_text(markdown, encoding="utf-8")
    return {"mode": "agent", "task_id": task_id, "markdown_url": markdown_url, "output_path": str(md_path)}


def parse_standard(source: str, out_base: Path, args: argparse.Namespace, token: str) -> dict[str, Any]:
    headers = auth_headers(token)
    payload = common_payload(args, standard=True)
    if is_url(source):
        payload["url"] = source
        result = request_json("POST", f"{BASE_URL}/api/v4/extract/task", payload, headers=headers)
        task_id = (result.get("data") or {}).get("task_id")
        if not task_id:
            raise MinerUError(f"MinerU standard did not return task_id: {result}")
        final = poll_standard_task(task_id, token, args.timeout, args.interval)
        task_or_batch = {"task_id": task_id}
    else:
        path = Path(source)
        file_item: dict[str, Any] = {"name": path.name, "data_id": path.name}
        if args.page_range:
            file_item["page_ranges"] = args.page_range
        file_item["is_ocr"] = args.ocr
        payload["files"] = [file_item]
        result = request_json("POST", f"{BASE_URL}/api/v4/file-urls/batch", payload, headers=headers)
        data = result.get("data") or {}
        batch_id = data.get("batch_id")
        urls = data.get("file_urls") or []
        if not batch_id or not urls:
            raise MinerUError(f"MinerU standard did not return upload URL: {result}")
        put_file(urls[0], path)
        final = poll_standard_batch(batch_id, token, args.timeout, args.interval)
        task_or_batch = {"batch_id": batch_id}
    zip_url = final.get("full_zip_url")
    if not zip_url:
        raise MinerUError(f"MinerU standard completed without full_zip_url: {final}")
    zip_bytes = download_bytes(zip_url)
    zip_path = out_base.parent / "_zip" / f"{out_base.name}.zip"
    extract_dir = out_base.parent / "_extracted" / out_base.name
    markdown = extract_full_md(zip_bytes, zip_path, extract_dir)
    md_path = out_base.with_suffix(".md")
    md_path.write_text(markdown, encoding="utf-8")
    return {
        "mode": "standard",
        **task_or_batch,
        "full_zip_url": zip_url,
        "zip_path": str(zip_path),
        "extract_dir": str(extract_dir),
        "output_path": str(md_path),
    }


def append_log(output_dir: Path, record: dict[str, Any]) -> None:
    log_path = output_dir / "_mineru_parse_log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def convert_one(source: str, args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(source)
    out_base = output_dir / stem
    md_path = out_base.with_suffix(".md")
    meta_path = out_base.with_suffix(".meta.json")
    fingerprint = source_fingerprint(source)

    if md_path.exists() and meta_path.exists() and not args.force:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
        if meta.get("source_fingerprint") == fingerprint:
            return {"status": "cached", "source": source, "output_path": str(md_path), "meta_path": str(meta_path)}

    token = os.environ.get(args.token_env, "").strip()
    mode = args.mode
    if mode == "auto":
        mode = "standard" if token else "agent"
    if mode == "standard" and not token:
        raise MinerUError(f"--mode standard requires {args.token_env}")

    started = time.time()
    if mode == "standard":
        result = parse_standard(source, out_base, args, token)
    elif mode == "agent":
        result = parse_agent(source, out_base, args)
    else:
        raise MinerUError(f"Unknown mode: {mode}")

    record = {
        "status": "completed",
        "source": source,
        "source_fingerprint": fingerprint,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_seconds": round(time.time() - started, 2),
        "parameters": {
            "language": args.language,
            "enable_table": args.enable_table,
            "enable_formula": args.enable_formula,
            "is_ocr": args.ocr,
            "page_range": args.page_range,
            "model_version": args.model_version if mode == "standard" else None,
        },
        **result,
    }
    meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    append_log(output_dir, record)
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert PDFs/documents to Markdown with MinerU.")
    parser.add_argument("inputs", nargs="+", help="Local file paths or HTTP(S) URLs.")
    parser.add_argument("--output-dir", default="related_work/pdf_markdown", help="Directory for Markdown and metadata.")
    parser.add_argument("--mode", choices=["auto", "agent", "standard"], default="auto")
    parser.add_argument("--token-env", default="MINERU_API_TOKEN", help="Environment variable holding the MinerU API token.")
    parser.add_argument("--model-version", choices=["pipeline", "vlm", "MinerU-HTML"], default="vlm")
    parser.add_argument("--language", default="ch")
    parser.add_argument("--page-range", default="", help="Page range, e.g. 1-10. Mapped to page_range/page_ranges per API.")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR.")
    parser.add_argument("--disable-table", dest="enable_table", action="store_false", help="Disable table recognition.")
    parser.add_argument("--disable-formula", dest="enable_formula", action="store_false", help="Disable formula recognition.")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--interval", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="Ignore cached Markdown and parse again.")
    parser.set_defaults(enable_table=True, enable_formula=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = []
    had_error = False
    for source in args.inputs:
        if not is_url(source) and not Path(source).exists():
            record = {"status": "failed", "source": source, "error": "Input file does not exist"}
            print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
            results.append(record)
            had_error = True
            continue
        try:
            record = convert_one(source, args)
            print(json.dumps(record, ensure_ascii=False))
            results.append(record)
        except Exception as exc:
            record = {"status": "failed", "source": source, "error": str(exc)}
            print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
            results.append(record)
            had_error = True
    summary = {"status": "failed" if had_error else "completed", "results": results}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
