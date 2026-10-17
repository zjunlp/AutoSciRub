#!/usr/bin/env python3
"""Retrieve papers for agent-authored queries with complete query provenance.

The stable interface is intentionally small:

    agent queries -> normalized papers + retrieval trace

Providers are configured in YAML. Credentials are read only from environment
variables and are never written to either output artifact.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "2.0"
SKILL_VERSION = "autoscirub-rcbench-0.1.0"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ARXIV_ID_RE = re.compile(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?", re.IGNORECASE)
GENERIC_QUERY_TERMS = {
    "analysis", "approach", "data", "dataset", "deep", "evaluation", "experiment",
    "framework", "learning", "machine", "method", "model", "network", "paper",
    "prediction", "result", "science", "scientific", "study", "system", "using",
}


class ProviderSkipped(RuntimeError):
    """A configured provider cannot run, usually because credentials are absent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read the retrieval config") from exc
    if not path.is_file():
        raise FileNotFoundError(f"Retrieval config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Retrieval config must contain a YAML object: {path}")
    return data


def env_value(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_title(title: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_space(title).lower()).strip()


def normalize_doi(value: Any) -> str:
    text = normalize_space(value)
    if not text:
        return ""
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.IGNORECASE)
    match = DOI_RE.search(text)
    if not match:
        return ""
    doi = match.group(0).rstrip(".,;)]}").lower()
    if "article-pdf/doi/" in text.lower():
        doi = re.sub(r"/\d{6,}/[^/]+$", "", doi)
    doi = re.sub(r"/(?:abstract|full|html|meta|pdf|supplementary)$", "", doi)
    doi = re.sub(r"\.pdf$", "", doi)
    return doi


def extract_doi(*values: Any) -> str:
    for value in values:
        doi = normalize_doi(value)
        if doi:
            return doi
    return ""


def normalize_arxiv_id(value: Any) -> str:
    text = normalize_space(value).replace(".pdf", "")
    if not text:
        return ""
    prefixed = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)([^?#\s]+)", text, flags=re.IGNORECASE)
    if prefixed:
        candidate = prefixed.group(1).strip("/")
        match = ARXIV_ID_RE.fullmatch(candidate)
        if match:
            return re.sub(r"v\d+$", "", match.group(0), flags=re.IGNORECASE).lower()
    direct = ARXIV_ID_RE.fullmatch(text.strip())
    if direct:
        return re.sub(r"v\d+$", "", direct.group(0), flags=re.IGNORECASE).lower()
    modern = re.search(r"(?<![\d.])(\d{4}\.\d{4,5}(?:v\d+)?)(?!\d)", text, flags=re.IGNORECASE)
    if modern:
        return re.sub(r"v\d+$", "", modern.group(1), flags=re.IGNORECASE).lower()
    return ""


def normalize_authors(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"\s*(?:;|\band\b)\s*", value)
        return [normalize_space(part) for part in parts if normalize_space(part)]
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for item in value:
        if isinstance(item, str):
            name = normalize_space(item)
        elif isinstance(item, dict):
            name = normalize_space(
                item.get("name")
                or item.get("display_name")
                or (item.get("author") or {}).get("display_name")
            )
        else:
            name = ""
        if name and name not in authors:
            authors.append(name)
    return authors


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    body = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response from {url}: {raw[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected a JSON object from {url}, got {type(parsed).__name__}")
    return parsed


def make_paper(
    *,
    title: Any,
    provider: str,
    abstract: Any = "",
    authors: Any = None,
    url: Any = "",
    pdf_url: Any = "",
    doi: Any = "",
    arxiv_id: Any = "",
    published: Any = "",
    score: Any = 0.0,
    citations: Any = 0,
    source_type: str = "paper",
    provider_id: Any = "",
) -> dict[str, Any] | None:
    clean_title = normalize_space(title)
    if not clean_title:
        return None
    clean_url = normalize_space(url)
    clean_pdf_url = normalize_space(pdf_url)
    clean_doi = extract_doi(doi, clean_url, clean_pdf_url)
    clean_arxiv = normalize_arxiv_id(arxiv_id) or normalize_arxiv_id(clean_url) or normalize_arxiv_id(clean_pdf_url)
    if not clean_url:
        if clean_doi:
            clean_url = f"https://doi.org/{clean_doi}"
        elif clean_arxiv:
            clean_url = f"https://arxiv.org/abs/{clean_arxiv}"
    return {
        "title": clean_title,
        "abstract": normalize_space(abstract),
        "authors": normalize_authors(authors),
        "url": clean_url,
        "pdf_url": clean_pdf_url,
        "doi": clean_doi,
        "arxiv_id": clean_arxiv,
        "published": normalize_space(published),
        "source_type": source_type,
        "provider": provider,
        "provider_id": normalize_space(provider_id),
        "provider_score": as_float(score),
        "citations": as_int(citations, 0),
    }


def search_arxiv(query: str, limit: int, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    search_query = query if re.search(r"\b(?:all|ti|au|abs|cat):", query) else f"all:{query}"
    params = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "start": 0,
            "max_results": max(1, min(limit, 50)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    base_url = normalize_space(config.get("base_url")) or "https://export.arxiv.org/api/query"
    request = urllib.request.Request(f"{base_url}?{params}", headers={"Accept": "application/atom+xml"})
    timeout = as_float(config.get("timeout_seconds"), 30)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except Exception as exc:
        raise RuntimeError(f"arXiv request failed: {exc}") from exc
    root = ET.fromstring(raw)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        entry_url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        arxiv_id = normalize_arxiv_id(entry_url)
        paper = make_paper(
            title=entry.findtext("atom:title", default="", namespaces=ns),
            abstract=entry.findtext("atom:summary", default="", namespaces=ns),
            authors=[
                author.findtext("atom:name", default="", namespaces=ns)
                for author in entry.findall("atom:author", ns)
            ],
            url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else entry_url,
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "",
            doi=entry.findtext("arxiv:doi", default="", namespaces=ns),
            arxiv_id=arxiv_id,
            published=entry.findtext("atom:published", default="", namespaces=ns),
            provider="arxiv",
            source_type="preprint",
            provider_id=arxiv_id,
        )
        if paper:
            papers.append(paper)
    return papers, {}


def reconstruct_openalex_abstract(inverted: Any) -> str:
    if not isinstance(inverted, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        if isinstance(positions, list):
            positioned.extend((as_int(position, 0), str(word)) for position in positions)
    positioned.sort(key=lambda pair: pair[0])
    return " ".join(word for _, word in positioned)


def search_openalex(query: str, limit: int, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params = {"search": query, "per-page": str(max(1, min(limit, 50)))}
    email = env_value(config.get("email_env"))
    if email:
        params["mailto"] = email
    base_url = normalize_space(config.get("base_url")) or "https://api.openalex.org/works"
    data = request_json(
        f"{base_url}?{urllib.parse.urlencode(params)}",
        timeout=as_float(config.get("timeout_seconds"), 30),
    )
    papers: list[dict[str, Any]] = []
    for work in (data.get("results") or [])[:limit]:
        if not isinstance(work, dict):
            continue
        primary = work.get("primary_location") or {}
        best_oa = work.get("best_oa_location") or {}
        doi = normalize_doi(work.get("doi"))
        paper = make_paper(
            title=work.get("title"),
            abstract=reconstruct_openalex_abstract(work.get("abstract_inverted_index")),
            authors=work.get("authorships"),
            url=doi and f"https://doi.org/{doi}" or primary.get("landing_page_url") or work.get("id"),
            pdf_url=best_oa.get("pdf_url") or primary.get("pdf_url") or "",
            doi=doi,
            published=work.get("publication_date") or work.get("publication_year"),
            provider="openalex",
            provider_id=work.get("id"),
            score=work.get("relevance_score"),
            citations=work.get("cited_by_count"),
        )
        if paper:
            papers.append(paper)
    return papers, {"result_count_reported": data.get("meta", {}).get("count")}


def search_semantic_scholar(
    query: str, limit: int, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "query": query,
            "limit": str(max(1, min(limit, 100))),
            "fields": "title,abstract,authors,url,externalIds,year,citationCount,publicationTypes,openAccessPdf",
        }
    )
    base_url = normalize_space(config.get("base_url")) or "https://api.semanticscholar.org/graph/v1/paper/search"
    headers: dict[str, str] = {}
    api_key = env_value(config.get("api_key_env"))
    if api_key:
        headers["x-api-key"] = api_key
    data = request_json(
        f"{base_url}?{params}",
        headers=headers,
        timeout=as_float(config.get("timeout_seconds"), 30),
    )
    papers: list[dict[str, Any]] = []
    for item in (data.get("data") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        external = item.get("externalIds") or {}
        oa_pdf = item.get("openAccessPdf") or {}
        paper = make_paper(
            title=item.get("title"),
            abstract=item.get("abstract"),
            authors=item.get("authors"),
            url=item.get("url"),
            pdf_url=oa_pdf.get("url"),
            doi=external.get("DOI"),
            arxiv_id=external.get("ArXiv"),
            published=item.get("year"),
            provider="semantic_scholar",
            provider_id=item.get("paperId"),
            citations=item.get("citationCount"),
        )
        if paper:
            papers.append(paper)
    return papers, {"result_count_reported": data.get("total")}


def search_tavily(query: str, limit: int, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = env_value(config.get("api_key_env"))
    if not api_key:
        raise ProviderSkipped(f"missing {config.get('api_key_env') or 'TAVILY_API_KEY'}")
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": normalize_space(config.get("search_depth")) or "basic",
        "max_results": max(1, min(limit, 20)),
        "include_answer": False,
        "include_raw_content": False,
    }
    base_url = normalize_space(config.get("base_url")) or "https://api.tavily.com/search"
    data = request_json(
        base_url,
        method="POST",
        payload=payload,
        timeout=as_float(config.get("timeout_seconds"), 30),
    )
    papers: list[dict[str, Any]] = []
    for item in (data.get("results") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        paper = make_paper(
            title=item.get("title"),
            abstract=item.get("content"),
            url=item.get("url"),
            provider="tavily",
            source_type="web",
            score=item.get("score"),
        )
        if paper:
            papers.append(paper)
    return papers, {"response_time": data.get("response_time")}


def nested_value(data: Any, path: tuple[str, ...]) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def find_sciatlas_papers(data: dict[str, Any]) -> list[dict[str, Any]]:
    known_paths = (
        ("result", "sources", "kg", "papers"),
        ("result", "papers"),
        ("papers",),
    )
    for path in known_paths:
        value = nested_value(data, path)
        if isinstance(value, list) and any(isinstance(item, dict) for item in value):
            return [item for item in value if isinstance(item, dict)]

    found: list[list[dict[str, Any]]] = []

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(value, list):
            rows = [item for item in value if isinstance(item, dict)]
            if rows and any(item.get("title") or item.get("paper_title") for item in rows):
                found.append(rows)
                return
            for item in value[:10]:
                walk(item, depth + 1)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child, depth + 1)

    walk(data)
    return found[0] if found else []


def search_sciatlas(query: str, limit: int, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = env_value(config.get("api_key_env"))
    if not api_key:
        raise ProviderSkipped(f"missing {config.get('api_key_env') or 'SCIATLAS_API_KEY'}")
    base_url = env_value(config.get("base_url_env")) or normalize_space(config.get("base_url"))
    base_url = (base_url or "http://sciatlas.openkg.cn").rstrip("/")
    mode = normalize_space(config.get("retrieval_mode")) or "keyword"
    if mode != "keyword":
        raise RuntimeError(f"{SKILL_VERSION} supports only SciAtlas keyword retrieval")
    top_k = min(limit, max(1, as_int(config.get("top_k"), 5)))
    payload = {
        "plan": {
            "query_text": query,
            "source_type": "idea_text",
            "source_title": None,
            "keywords": [{"text": query, "score": 8}],
            "titles": [],
            "reference_titles": [],
        },
        "options": {"top_k": top_k, "retrieval_mode": "keyword"},
    }
    data = request_json(
        f"{base_url}/v1/search",
        method="POST",
        payload=payload,
        headers={"Authorization": f"Bearer {api_key}", "X-API-Key": api_key},
        timeout=as_float(config.get("timeout_seconds"), 120),
    )
    papers: list[dict[str, Any]] = []
    for item in find_sciatlas_papers(data)[:top_k]:
        external = item.get("external_ids") or item.get("externalIds") or {}
        if not isinstance(external, dict):
            external = {}
        venue = item.get("venue") or {}
        if not isinstance(venue, dict):
            venue = {}
        paper = make_paper(
            title=item.get("title") or item.get("paper_title") or item.get("name"),
            abstract=item.get("abstract") or item.get("summary") or item.get("description"),
            authors=item.get("authors") or item.get("author_names"),
            url=item.get("url") or item.get("paper_url") or item.get("landing_page_url"),
            pdf_url=item.get("pdf_url") or item.get("open_access_pdf"),
            doi=item.get("doi") or external.get("DOI") or external.get("doi"),
            arxiv_id=item.get("arxiv_id") or external.get("ArXiv") or external.get("arxiv"),
            published=item.get("published") or item.get("publication_date") or item.get("year"),
            provider="sciatlas",
            provider_id=item.get("paper_id") or item.get("id") or item.get("openalex_id"),
            score=item.get("score") or item.get("relevance_score") or item.get("final_score"),
            citations=item.get("citations") or item.get("citation_count") or item.get("cited_by_count"),
        )
        if paper:
            papers.append(paper)
    return papers, {"request_id": data.get("request_id"), "api_status": data.get("status")}


def local_title(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt"}:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for _ in range(40):
                    line = handle.readline()
                    if not line:
                        break
                    heading = re.match(r"^#\s+(.+?)\s*$", line)
                    if heading:
                        return normalize_space(heading.group(1))
        except OSError:
            pass
    return path.stem


def safe_workspace_path(raw_path: str | Path, workspace: Path, excluded_paths: list[str] | None = None) -> Path:
    """Reject hidden evidence and symlink escapes before opening or traversing it."""
    workspace = workspace.resolve()
    lexical = Path(os.path.abspath(workspace / raw_path))
    resolved = lexical.resolve()
    for path in (lexical, resolved):
        try:
            relative = path.relative_to(workspace)
        except ValueError as exc:
            raise ValueError(f"Path must remain inside the task workspace: {raw_path}") from exc
        if any("checklist" in part.lower() or "target_study" in part.lower()
               or "target-study" in part.lower() for part in relative.parts):
            raise ValueError(f"Excluded benchmark evidence path: {raw_path}")
        for item in excluded_paths or []:
            excluded = Path(os.path.abspath(workspace / item))
            for blocked_path in (excluded, excluded.resolve()):
                if path == blocked_path or blocked_path in path.parents:
                    raise ValueError(f"Explicitly excluded path: {raw_path}")
    return resolved


def collect_local_literature(paths: list[str], limit: int, *, workspace: Path | None = None,
                             excluded_paths: list[str] | None = None) -> list[dict[str, Any]]:
    workspace = (workspace or Path.cwd()).resolve()
    allowed = {".pdf", ".md", ".txt", ".json"}
    files: list[Path] = []
    for raw_path in paths:
        # Explicit unsafe roots are configuration errors. Unsafe descendants are
        # pruned before os.walk descends into them or local_title opens them.
        path = safe_workspace_path(raw_path, workspace, excluded_paths)
        if not path.exists():
            continue
        if path.is_dir():
            for root, dirs, names in os.walk(path, followlinks=False):
                safe_dirs = []
                for name in sorted(dirs):
                    child = Path(root) / name
                    try:
                        safe_workspace_path(child, workspace, excluded_paths)
                    except ValueError:
                        continue
                    if not child.is_symlink():
                        safe_dirs.append(name)
                dirs[:] = safe_dirs
                for name in sorted(names):
                    try:
                        files.append(safe_workspace_path(Path(root) / name, workspace, excluded_paths))
                    except ValueError:
                        continue
        else:
            files.append(path)
    papers: list[dict[str, Any]] = []
    if limit <= 0:
        return papers
    for path in dict.fromkeys(files):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        paper = make_paper(
            title=local_title(path),
            url=str(path.resolve()),
            pdf_url=str(path.resolve()) if path.suffix.lower() == ".pdf" else "",
            provider="local_literature",
            source_type="local_literature",
            provider_id=str(path.resolve()),
        )
        if paper:
            papers.append(paper)
        if len(papers) >= limit:
            break
    return papers


PROVIDER_FUNCTIONS: dict[
    str, Callable[[str, int, dict[str, Any]], tuple[list[dict[str, Any]], dict[str, Any]]]
] = {
    "arxiv": search_arxiv,
    "openalex": search_openalex,
    "semantic_scholar": search_semantic_scholar,
    "tavily": search_tavily,
    "sciatlas": search_sciatlas,
}


def load_query_plan(path: Path) -> list[Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("queries"), list):
        return data["queries"]
    raise ValueError("Query plan must be a JSON list or an object containing a queries list")


def normalize_queries(raw_queries: list[Any], max_queries: int) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    identities: dict[str, str] = {}
    for index, raw in enumerate(raw_queries, start=1):
        if isinstance(raw, str):
            text = normalize_space(raw)
            item: dict[str, Any] = {}
        elif isinstance(raw, dict):
            text = normalize_space(raw.get("query") or raw.get("text"))
            item = raw
        else:
            continue
        dedupe_key = text.lower()
        if not text:
            continue
        query_id = normalize_space(item.get("query_id")) or "q-" + hashlib.sha256(dedupe_key.encode()).hexdigest()[:16]
        if query_id in identities and identities[query_id] != text:
            raise ValueError(f"Query ID {query_id!r} cannot be reused with changed query text")
        identities[query_id] = text
        if dedupe_key in seen:
            previous = seen[dedupe_key]
            if item.get("query_id") and previous["query_id"] != query_id:
                raise ValueError("The same query text cannot have multiple query IDs")
            if item.get("stage") and item["stage"] != previous["stage"]:
                raise ValueError(f"Query {query_id!r} cannot change stage on resume")
            continue
        stage = normalize_space(item.get("stage")) or "initial"
        if stage not in {"initial", "followup"}:
            raise ValueError(f"Invalid query stage: {stage!r}")
        key_terms = item.get("key_terms") or []
        if not isinstance(key_terms, list):
            key_terms = []
        queries.append(
            {
                "query_id": query_id,
                "stage": stage,
                "query": text,
                "target_signal": normalize_space(item.get("target_signal")),
                "key_terms": [normalize_space(term) for term in key_terms if normalize_space(term)],
                "priority": max(1, as_int(item.get("priority"), index)),
                "parent_query_id": normalize_space(item.get("parent_query_id")) or None,
            }
        )
        seen[dedupe_key] = queries[-1]
    if len(queries) > max_queries:
        raise ValueError(f"Query plan has {len(queries)} unique queries; max_queries_per_task is {max_queries}. "
                         "Reduce the plan or explicitly increase the configured budget; queries are never truncated.")
    queries.sort(key=lambda query: (query["priority"], query["query_id"]))
    return queries


def validate_query_budgets(queries: list[dict[str, Any]], config: dict[str, Any]) -> None:
    limits = (config.get("retrieval") or {}).get("limits") or {}
    total = max(0, as_int(limits.get("max_queries_per_task"), 4))
    if len(queries) > total:
        raise ValueError(f"Query count {len(queries)} exceeds max_queries_per_task={total}")
    workflow = config.get("workflow") or {}
    for stage in ("initial", "followup"):
        key = f"max_{stage}_queries"
        if key in workflow:
            count = sum(query["stage"] == stage for query in queries)
            if count > as_int(workflow[key], 0):
                raise ValueError(f"{stage} query count {count} exceeds workflow.{key}={workflow[key]}")


def _identifier_signal(text: str) -> int:
    """Return a mechanical specificity signal for acronyms, numbers, and names."""
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+_.-]*", text)
    score = 0
    for token in tokens:
        letters = re.sub(r"[^A-Za-z]", "", token)
        if any(char.isdigit() for char in token) or any(char in "+_.-" for char in token):
            score += 3
        if 2 <= len(letters) <= 16 and letters.isupper():
            score += 4
        elif any(char.isupper() for char in letters[1:]):
            score += 3
        elif len(letters) >= 9 and letters.lower() not in GENERIC_QUERY_TERMS:
            score += 1
    return score


def sciatlas_query_score(query: dict[str, Any]) -> float:
    """Rank agent-authored queries for SciAtlas without relying on q01/q02 order."""
    text = normalize_space(query.get("query"))
    key_terms = [normalize_space(term) for term in query.get("key_terms") or [] if normalize_space(term)]
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+_.-]*", text)
    quoted_phrases = re.findall(r'["“”]([^"“”]{3,100})["“”]', text)
    target_signal = normalize_space(query.get("target_signal")).lower()

    score = 12.0 if query.get("stage") == "followup" else 0.0
    score += min(12.0, float(_identifier_signal(text)))
    score += min(10.0, 5.0 * len(quoted_phrases))
    if (
        "named method" in target_signal
        or "named model" in target_signal
        or "method identity" in target_signal
        or "model identity" in target_signal
    ):
        score += 8.0
    elif "exact method" in target_signal:
        score += 7.0
    elif "exact" in target_signal:
        score += 3.0

    term_scores: list[float] = []
    for term in key_terms:
        term_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+_.-]*", term)
        generic_count = sum(word.lower() in GENERIC_QUERY_TERMS for word in term_words)
        current = 1.0 + min(3, max(0, len(term_words) - 1))
        current += min(6, _identifier_signal(term))
        current -= generic_count * 0.75
        term_scores.append(max(0.0, current))
    score += min(15.0, sum(sorted(term_scores, reverse=True)[:4]))

    generic_ratio = (
        sum(word.lower() in GENERIC_QUERY_TERMS for word in words) / len(words)
        if words else 1.0
    )
    short_acronyms = sum(
        2 <= len(re.sub(r"[^A-Za-z]", "", word)) <= 5
        and re.sub(r"[^A-Za-z]", "", word).isupper()
        for word in words
    )
    score -= max(0, len(words) - 12) * 0.75
    score -= max(0, short_acronyms - 3) * 2.0
    score -= generic_ratio * 4.0
    return round(score, 3)


def select_provider_queries(provider: str, queries: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Select the provider budget; SciAtlas favors discriminative query evidence."""
    if limit <= 0:
        return []
    if provider != "sciatlas":
        return queries[:limit]
    ranked = sorted(
        queries,
        key=lambda query: (
            -sciatlas_query_score(query),
            as_int(query.get("priority"), 10**9),
            normalize_space(query.get("query_id")),
        ),
    )
    return ranked[:limit]


def preliminary_canonical_id(paper: dict[str, Any]) -> str:
    if paper.get("doi"):
        return f"doi:{paper['doi']}"
    if paper.get("arxiv_id"):
        return f"arxiv:{paper['arxiv_id']}"
    title = normalize_title(paper.get("title"))
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]
    return f"title:{digest}" if title else ""


def blocked(paper: dict[str, Any], exclusions: dict[str, Any]) -> bool:
    normalized = normalize_title(paper.get("title"))
    for title in exclusions.get("blocked_titles") or []:
        if normalize_title(title) and normalize_title(title) in normalized:
            return True
    host = ""
    try:
        host = urllib.parse.urlparse(paper.get("url") or "").netloc.lower()
    except Exception:
        pass
    for domain in exclusions.get("blocked_domains") or []:
        if host.endswith(normalize_space(domain).lower().lstrip(".")):
            return True
    return False


def merge_papers(raw_hits: list[dict[str, Any]], rrf_k: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    groups: list[dict[str, Any]] = []
    doi_index: dict[str, int] = {}
    arxiv_index: dict[str, int] = {}
    title_index: dict[str, int] = {}
    hit_to_canonical: dict[str, str] = {}

    for paper in raw_hits:
        doi = paper.get("doi") or ""
        arxiv_id = paper.get("arxiv_id") or ""
        title_key = normalize_title(paper.get("title"))
        candidates = [
            doi_index.get(doi) if doi else None,
            arxiv_index.get(arxiv_id) if arxiv_id else None,
            title_index.get(title_key) if title_key else None,
        ]
        group_index = next((value for value in candidates if value is not None), None)
        if group_index is None:
            group_index = len(groups)
            groups.append(
                {
                    "title": paper.get("title") or "",
                    "abstract": paper.get("abstract") or "",
                    "authors": list(paper.get("authors") or []),
                    "url": paper.get("url") or "",
                    "pdf_url": paper.get("pdf_url") or "",
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                    "published": paper.get("published") or "",
                    "source_type": paper.get("source_type") or "paper",
                    "provider": paper.get("provider") or "",
                    "provider_id": paper.get("provider_id") or "",
                    "citations": as_int(paper.get("citations"), 0),
                    "providers": [],
                    "urls": [],
                    "retrieval_hits": [],
                    "fusion_score": 0.0,
                    "best_rank": 10**9,
                }
            )
        group = groups[group_index]
        if doi:
            doi_index[doi] = group_index
            group["doi"] = group.get("doi") or doi
        if arxiv_id:
            arxiv_index[arxiv_id] = group_index
            group["arxiv_id"] = group.get("arxiv_id") or arxiv_id
        if title_key:
            title_index[title_key] = group_index
        if len(paper.get("abstract") or "") > len(group.get("abstract") or ""):
            group["abstract"] = paper["abstract"]
        for author in paper.get("authors") or []:
            if author not in group["authors"]:
                group["authors"].append(author)
        for url in (paper.get("url"), paper.get("pdf_url")):
            if url and url not in group["urls"]:
                group["urls"].append(url)
        if not group.get("url") and paper.get("url"):
            group["url"] = paper["url"]
        if not group.get("pdf_url") and paper.get("pdf_url"):
            group["pdf_url"] = paper["pdf_url"]
        if not group.get("published") and paper.get("published"):
            group["published"] = paper["published"]
        group["citations"] = max(group["citations"], as_int(paper.get("citations"), 0))

        hit = dict(paper["_hit"])
        rank = max(1, as_int(hit.get("provider_rank"), 1))
        provider = hit["provider"]
        group["retrieval_hits"].append(hit)
        if provider not in group["providers"]:
            group["providers"].append(provider)
        group["fusion_score"] += 1.0 / (rrf_k + rank)
        if rank < group["best_rank"]:
            group["best_rank"] = rank
            group["provider"] = provider
            group["source_type"] = paper.get("source_type") or group["source_type"]

    for group in groups:
        group["providers"].sort()
        group["fusion_score"] = round(group["fusion_score"], 8)
        group["score"] = group["fusion_score"]
        group["canonical_id"] = preliminary_canonical_id(group)
        group["retrieval_hits"].sort(
            key=lambda hit: (hit.get("provider_rank", 10**9), hit.get("provider", ""), hit.get("query_id", ""))
        )
        for hit in group["retrieval_hits"]:
            hit_to_canonical[hit["hit_id"]] = group["canonical_id"]

    groups.sort(
        key=lambda paper: (
            -paper["fusion_score"],
            paper["best_rank"],
            -paper["citations"],
            normalize_title(paper["title"]),
        )
    )
    for rank, group in enumerate(groups, start=1):
        group["aggregate_rank"] = rank
    return groups, hit_to_canonical


def public_config(config: dict[str, Any], providers: list[str]) -> dict[str, Any]:
    retrieval = config.get("retrieval") or {}
    provider_config = retrieval.get("providers") or {}
    safe_providers: dict[str, Any] = {}
    for provider in providers:
        current = dict(provider_config.get(provider) or {})
        current.pop("api_key", None)
        safe_providers[provider] = current
    return {
        "enabled_sources": providers,
        "limits": retrieval.get("limits") or {},
        "providers": safe_providers,
    }


def attempt_parameters(provider: str, config: dict[str, Any], limit: int,
                       query: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"limit": limit}
    if provider == "sciatlas":
        result["retrieval_mode"] = "keyword"
        result["top_k"] = min(limit, max(1, as_int(config.get("top_k"), 5)))
        if query is not None:
            result["query_selection"] = "discriminative"
            result["query_selection_score"] = sciatlas_query_score(query)
    elif provider == "tavily":
        result["search_depth"] = normalize_space(config.get("search_depth")) or "basic"
    return result


def run(
    *,
    config: dict[str, Any],
    queries: list[dict[str, Any]],
    task_id: str,
    provider_override: list[str] | None,
    local_paths: list[str],
    existing_candidates: dict[str, Any] | None = None,
    existing_trace: dict[str, Any] | None = None,
    workspace: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    workspace = (workspace or Path.cwd()).resolve()
    retrieval = config.get("retrieval") or {}
    configured_providers = retrieval.get("providers") or {}
    enabled = provider_override or list(retrieval.get("enabled_sources") or [])
    enabled = [provider for provider in enabled if provider in configured_providers or provider == "local_literature"]
    limits = retrieval.get("limits") or {}
    default_limit = max(1, as_int(limits.get("max_results_per_query"), 8))
    exclusions = retrieval.get("exclusions") or {}
    excluded_paths = list(exclusions.get("excluded_paths") or [])
    queries = normalize_queries([*((existing_trace or {}).get("queries") or []), *queries],
                                max(0, as_int(limits.get("max_queries_per_task"), 4)))
    validate_query_budgets(queries, config)
    for previous in (existing_candidates, existing_trace):
        if previous and previous.get("task_id") != task_id:
            raise ValueError("Resume artifacts must belong to the current task_id")
    attempts: list[dict[str, Any]] = copy.deepcopy((existing_trace or {}).get("attempts") or [])
    initial_attempt_count = len(attempts)
    raw_hits: list[dict[str, Any]] = []

    for existing_paper in (existing_candidates or {}).get("all_sources") or []:
        if not isinstance(existing_paper, dict):
            continue
        for existing_hit in existing_paper.get("retrieval_hits") or []:
            if not isinstance(existing_hit, dict) or not existing_hit.get("hit_id"):
                continue
            restored = {
                key: value
                for key, value in existing_paper.items()
                if key
                not in {
                    "aggregate_rank",
                    "best_rank",
                    "canonical_id",
                    "fusion_score",
                    "providers",
                    "retrieval_hits",
                    "score",
                    "urls",
                    "used_for_goal_ids",
                }
            }
            restored["provider"] = existing_hit.get("provider") or restored.get("provider")
            restored["provider_score"] = existing_hit.get("provider_score", 0.0)
            restored["_hit"] = dict(existing_hit)
            raw_hits.append(restored)

    completed_request_ids = {
        attempt.get("request_id") for attempt in attempts if isinstance(attempt, dict)
    }

    if ("local_literature" in enabled and "local-literature" not in completed_request_ids
            and (configured_providers.get("local_literature") or {}).get("enabled", True)):
        local_config = configured_providers.get("local_literature") or {}
        paths = local_paths or list(local_config.get("paths") or [])
        started = time.monotonic()
        papers = collect_local_literature(paths, as_int(local_config.get("max_results"), 50),
                                         workspace=workspace, excluded_paths=excluded_paths)
        local_available = any(safe_workspace_path(path, workspace, excluded_paths).exists() for path in paths)
        attempt = {
            "request_id": "local-literature",
            "query_id": "local",
            "provider": "local_literature",
            "provider_query": None,
            "parameters": {"paths": paths},
            "started_at": utc_now(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "status": "success" if local_available else "skipped",
            "error": None if local_available else "No configured local literature path exists",
            "result_count": len(papers),
            "results": [],
        }
        for rank, paper in enumerate(papers, start=1):
            hit_id = f"local-literature:r{rank}"
            paper["_hit"] = {
                "hit_id": hit_id,
                "request_id": "local-literature",
                "query_id": "local",
                "provider": "local_literature",
                "provider_rank": rank,
                "provider_score": paper.get("provider_score", 0.0),
            }
            raw_hits.append(paper)
            attempt["results"].append(
                {
                    "hit_id": hit_id,
                    "provider_rank": rank,
                    "provider_score": paper.get("provider_score", 0.0),
                    "title": paper["title"],
                    "doi": paper.get("doi"),
                    "arxiv_id": paper.get("arxiv_id"),
                    "url": paper.get("url"),
                }
            )
        attempts.append(attempt)

    provider_budget_usage: dict[str, Any] = {}
    for provider in enabled:
        if provider == "local_literature":
            continue
        provider_config = configured_providers.get(provider) or {}
        if provider_config.get("enabled", True) is False:
            continue
        search = PROVIDER_FUNCTIONS.get(provider)
        if search is None:
            print(f"[WARN] unsupported provider in config: {provider}", file=sys.stderr)
            continue
        max_provider_queries = max(0, as_int(provider_config.get("max_queries"), len(queries)))
        provider_limit = max(1, as_int(provider_config.get("max_results"), default_limit))
        prior_requests = {attempt["request_id"] for attempt in attempts if attempt.get("provider") == provider}
        remaining = max(0, max_provider_queries - len(prior_requests))
        unattempted = [query for query in queries if f"{query['query_id']}-{provider}" not in completed_request_ids]
        provider_queries = select_provider_queries(provider, unattempted, remaining)
        provider_budget_usage[provider] = {
            "max_queries": max_provider_queries,
            "previous_unique_attempts": len(prior_requests),
            "remaining_before_run": remaining,
            "selected_query_ids": [query["query_id"] for query in provider_queries],
            "unselected_query_ids": [query["query_id"] for query in unattempted if query not in provider_queries],
        }
        for query in provider_queries:
            request_id = f"{query['query_id']}-{provider}"
            if request_id in completed_request_ids:
                continue
            started_at = utc_now()
            started = time.monotonic()
            attempt: dict[str, Any] = {
                "request_id": request_id,
                "query_id": query["query_id"],
                "provider": provider,
                "provider_query": query["query"],
                "parameters": attempt_parameters(provider, provider_config, provider_limit, query),
                "started_at": started_at,
                "elapsed_seconds": 0.0,
                "status": "error",
                "error": None,
                "result_count": 0,
                "response_meta": {},
                "results": [],
            }
            try:
                papers, response_meta = search(query["query"], provider_limit, provider_config)
                papers = [paper for paper in papers if not blocked(paper, exclusions)]
                attempt["status"] = "success"
                attempt["response_meta"] = {key: value for key, value in response_meta.items() if value is not None}
                attempt["result_count"] = len(papers)
                for rank, paper in enumerate(papers, start=1):
                    hit_id = f"{request_id}:r{rank}"
                    paper["_hit"] = {
                        "hit_id": hit_id,
                        "request_id": request_id,
                        "query_id": query["query_id"],
                        "provider": provider,
                        "provider_rank": rank,
                        "provider_score": paper.get("provider_score", 0.0),
                    }
                    raw_hits.append(paper)
                    attempt["results"].append(
                        {
                            "hit_id": hit_id,
                            "provider_rank": rank,
                            "provider_score": paper.get("provider_score", 0.0),
                            "title": paper["title"],
                            "doi": paper.get("doi"),
                            "arxiv_id": paper.get("arxiv_id"),
                            "url": paper.get("url"),
                        }
                    )
            except ProviderSkipped as exc:
                attempt["status"] = "skipped"
                attempt["error"] = str(exc)
            except Exception as exc:
                attempt["error"] = f"{type(exc).__name__}: {exc}"
                print(f"[WARN] {provider} failed for {query['query'][:80]}: {exc}", file=sys.stderr)
            attempt["elapsed_seconds"] = round(time.monotonic() - started, 3)
            attempts.append(attempt)
            completed_request_ids.add(request_id)
        provider_budget_usage[provider]["used_unique_attempts"] = len(prior_requests) + len(provider_queries)

    papers, hit_to_canonical = merge_papers(raw_hits, max(1, as_int(limits.get("rrf_k"), 60)))
    for attempt in attempts:
        for result in attempt["results"]:
            result["canonical_id"] = hit_to_canonical.get(result["hit_id"], preliminary_canonical_id(result))

    for paper in papers:
        paper["used_for_goal_ids"] = [task_id]

    core_limit = max(1, as_int(limits.get("max_core_sources"), 5))
    supplemental_limit = max(0, as_int(limits.get("max_supplemental_sources"), 8))
    query_metrics: list[dict[str, Any]] = []
    for query in queries:
        query_attempts = [attempt for attempt in attempts if attempt["query_id"] == query["query_id"]]
        canonical_ids = {
            result.get("canonical_id")
            for attempt in query_attempts
            for result in attempt["results"]
            if result.get("canonical_id")
        }
        query_metrics.append(
            {
                "query_id": query["query_id"],
                "attempt_count": len(query_attempts),
                "successful_attempts": sum(attempt["status"] == "success" for attempt in query_attempts),
                "raw_result_count": sum(attempt["result_count"] for attempt in query_attempts),
                "unique_paper_count": len(canonical_ids),
                "possible_hit": None,
                "final_candidate_hit": None,
            }
        )

    config_used = public_config(config, enabled)
    candidates = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "task_id": task_id,
        "skill_version": SKILL_VERSION,
        "config_used": config_used,
        "queries": queries,
        "goals": [
            {
                "goal_id": task_id,
                "title": queries[0]["query"] if queries else task_id,
                "queries": [query["query"] for query in queries],
            }
        ],
        "core_sources": papers[:core_limit],
        "supplemental_sources": papers[core_limit : core_limit + supplemental_limit],
        "all_sources": papers,
    }
    trace = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "task_id": task_id,
        "skill_version": SKILL_VERSION,
        "queries": queries,
        "config_used": config_used,
        "attempts": attempts,
        "papers": [
            {
                "aggregate_rank": paper["aggregate_rank"],
                "canonical_id": paper["canonical_id"],
                "title": paper["title"],
                "doi": paper.get("doi"),
                "arxiv_id": paper.get("arxiv_id"),
                "providers": paper["providers"],
                "fusion_score": paper["fusion_score"],
                "retrieval_hits": paper["retrieval_hits"],
            }
            for paper in papers
        ],
        "query_metrics": query_metrics,
        "budget_usage": {
            "query_budget_semantics": "Cumulative unique queries, including prior resume rounds; excess is rejected.",
            "provider_budget_semantics": "Cumulative unique attempts, including errors/skips; no automatic retries.",
            "workflow": config.get("workflow") or {},
            "providers": provider_budget_usage,
        },
        "summary": {
            "query_count": len(queries),
            "attempt_count": len(attempts),
            "successful_attempts": sum(attempt["status"] == "success" for attempt in attempts),
            "skipped_attempts": sum(attempt["status"] == "skipped" for attempt in attempts),
            "failed_attempts": sum(attempt["status"] == "error" for attempt in attempts),
            "raw_result_count": len(raw_hits),
            "unique_paper_count": len(papers),
            "new_attempt_count": len(attempts) - initial_attempt_count,
            "new_successful_attempts": sum(attempt["status"] == "success" for attempt in attempts[initial_attempt_count:]),
        },
    }
    return candidates, trace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve normalized papers for agent-authored queries and save query-level provenance."
    )
    parser.add_argument("--config", required=True, help="Retrieval provider YAML")
    parser.add_argument("--workspace", default=".", help="Task workspace; local inputs and output paths are relative to it")
    parser.add_argument("--query", action="append", default=[], help="Agent query; repeat for multiple queries")
    parser.add_argument("--query-plan", help="JSON query plan containing strings or structured query objects")
    parser.add_argument("--task-id", default="TASK", help="Task identifier recorded in outputs")
    parser.add_argument("--provider", action="append", help="Restrict retrieval to selected provider(s)")
    parser.add_argument("--local-path", action="append", default=[], help="Local literature path; repeatable")
    parser.add_argument("--out", default="outputs/literature_candidates.json", help="Normalized paper output")
    parser.add_argument("--trace-out", default="outputs/retrieval_trace.json", help="Query-level trace output")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse existing output/trace and retrieve only newly added queries",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    config_path = Path(args.config).absolute()
    for candidate in (config_path, config_path.resolve()):
        if any("checklist" in part.lower() or "target_study" in part.lower()
               or "target-study" in part.lower() for part in candidate.parts):
            raise ValueError(f"Excluded benchmark evidence path: {args.config}")
    config = load_config(config_path)
    exclusions = ((config.get("retrieval") or {}).get("exclusions") or {}).get("excluded_paths") or []
    out_path = safe_workspace_path(args.out, workspace, exclusions)
    trace_path = safe_workspace_path(args.trace_out, workspace, exclusions)
    if out_path == trace_path:
        raise ValueError("--out and --trace-out must be different files")
    failed_out = safe_workspace_path(out_path.with_name(out_path.stem + ".failed" + out_path.suffix), workspace, exclusions)
    failed_trace = safe_workspace_path(trace_path.with_name(trace_path.stem + ".failed" + trace_path.suffix), workspace, exclusions)
    existing_candidates: dict[str, Any] | None = None
    existing_trace: dict[str, Any] | None = None
    raw_queries: list[Any] = []
    base_trace_hash = hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path.is_file() else None
    if args.resume and (out_path.exists() or trace_path.exists()):
        if not out_path.is_file() or not trace_path.is_file():
            raise SystemExit("--resume requires both the existing output and trace files")
        existing_candidates = json.loads(out_path.read_text(encoding="utf-8"))
        existing_trace = json.loads(trace_path.read_text(encoding="utf-8"))
    if args.resume and failed_out.is_file() and failed_trace.is_file():
        failure_checkpoint = json.loads(failed_trace.read_text(encoding="utf-8"))
        # Resume failed attempts too: preserving the good output must never
        # silently reset the provider budget or retry a failed request.
        if (failure_checkpoint.get("resume_base_sha256") == base_trace_hash
                and failure_checkpoint.get("task_id") == (normalize_space(args.task_id) or "TASK")):
            existing_candidates = json.loads(failed_out.read_text(encoding="utf-8"))
            existing_trace = failure_checkpoint
    if existing_trace:
        raw_queries.extend(existing_trace.get("queries") or [])
    if args.query_plan:
        raw_queries.extend(load_query_plan(safe_workspace_path(args.query_plan, workspace, exclusions)))
    raw_queries.extend(args.query)
    limits = (config.get("retrieval") or {}).get("limits") or {}
    queries = normalize_queries(raw_queries, max(0, as_int(limits.get("max_queries_per_task"), 4)))
    validate_query_budgets(queries, config)
    retrieval = config.get("retrieval") or {}
    local_config = (retrieval.get("providers") or {}).get("local_literature") or {}
    enabled = args.provider or retrieval.get("enabled_sources") or []
    local_enabled = ("local_literature" in enabled and local_config.get("enabled", True)
                     and bool(args.local_path or local_config.get("paths")))
    if not queries and not local_enabled:
        raise SystemExit("Provide at least one --query, --query-plan, or --local-path")
    candidates, trace = run(
        config=config,
        queries=queries,
        task_id=normalize_space(args.task_id) or "TASK",
        provider_override=args.provider,
        local_paths=args.local_path,
        existing_candidates=existing_candidates,
        existing_trace=existing_trace,
        workspace=workspace,
    )
    summary = trace["summary"]
    previous_failed = ((existing_trace or {}).get("summary") or {}).get("run_status") == "failed"
    failed = (summary["new_attempt_count"] > 0 and summary["new_successful_attempts"] == 0
              or summary["successful_attempts"] == 0
              or summary["new_attempt_count"] == 0 and previous_failed)
    summary["run_status"] = "failed" if failed else ("completed" if summary["new_attempt_count"] else "no_new_attempts")
    if failed:
        trace["resume_base_sha256"] = base_trace_hash
        out_path, trace_path = failed_out, failed_trace
    out_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {summary['unique_paper_count']} unique papers from "
        f"{summary['successful_attempts']}/{summary['attempt_count']} successful attempts to {out_path}"
    )
    print(f"wrote retrieval trace to {trace_path}")
    if failed:
        print("All new retrieval attempts failed/skipped, or no provider succeeded; existing outputs were preserved. "
              "Failure diagnostics count against resume budgets.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Retrieval failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
