#!/usr/bin/env python3
"""Run lightweight literature retrieval for AutoSciRub grounding.

Supports: arxiv, openalex, semantic_scholar, tavily, local_literature.
All credentials come from environment variables named in the config file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "state_dir": ".autoscirub",
    "retrieval": {
        "enabled_sources": ["local_literature", "arxiv", "openalex", "semantic_scholar", "tavily", "web"],
        "providers": {
            "arxiv": {"enabled": True},
            "openalex": {"enabled": True, "email_env": "OPENALEX_EMAIL"},
            "semantic_scholar": {"enabled": True, "api_key_env": "SEMANTIC_SCHOLAR_API_KEY"},
            "tavily": {"enabled": False, "api_key_env": "TAVILY_API_KEY"},
        },
        "limits": {
            "max_queries_per_goal": 5,
            "max_core_sources": 7,
            "max_supplemental_sources": 10,
            "max_results_per_query": 10,
        },
        "exclusions": {
            "excluded_paths": [],
            "blocked_titles": [],
            "blocked_domains": [],
        },
    },
}


def try_load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        return simple_yaml(path.read_text(encoding="utf-8"))
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def simple_yaml(text: str) -> dict:
    """Minimal YAML reader for the current sources.example shape.

    Supports nesting via indentation, lists starting with '- ', and string values.
    Falls back to DEFAULT_CONFIG on failure.
    """
    root: dict = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    lines = text.splitlines()
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            value = parse_scalar(line[2:].strip())
            if isinstance(parent, list):
                parent.append(value)
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            new_container: Any = {}
            if isinstance(parent, dict):
                parent[key] = new_container
            stack.append((indent, new_container))
        else:
            parsed = parse_scalar(value)
            if isinstance(parent, dict):
                parent[key] = parsed
    return root


def parse_scalar(value: str) -> Any:
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None", "~"):
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None) -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if config_path and config_path.exists():
        override = try_load_yaml(config_path)
        config = deep_merge(config, override)
    return config


def get_env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    return value if value else None


def http_get_json(url: str, headers: dict | None = None, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response from {url}: {raw[:200]}") from exc


def http_post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response from {url}: {raw[:200]}") from exc


def safe_get(d: dict, *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def is_blocked(title: str, blocked_titles: list[str], blocked_domains: list[str], url: str | None = None) -> bool:
    norm = norm_title(title or "")
    for blocked in blocked_titles:
        if blocked and norm_title(blocked) in norm:
            return True
    if url and blocked_domains:
        try:
            host = urllib.parse.urlparse(url).netloc.lower()
        except Exception:
            host = ""
        for domain in blocked_domains:
            if domain and host.endswith(domain.lower().lstrip(".")):
                return True
    return False


def search_arxiv(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max(1, min(limit, 50)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"http://export.arxiv.org/api/query?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/atom+xml"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as exc:
        raise RuntimeError(f"arXiv request failed: {exc}") from exc
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: list[dict] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        pdf_id = entry.findtext("atom:id", default="", namespaces=ns) or ""
        authors = [a.findtext("atom:name", default="", namespaces=ns) or "" for a in entry.findall("atom:author", ns)]
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        results.append({
            "title": title,
            "abstract": summary,
            "authors": authors,
            "url": pdf_id.replace("http://arxiv.org/abs/", "https://arxiv.org/abs/"),
            "pdf_url": pdf_id.replace("http://arxiv.org/abs/", "https://arxiv.org/pdf/") + ".pdf" if pdf_id else "",
            "published": published,
            "source_type": "preprint",
            "provider": "arxiv",
            "score": 0.0,
        })
    return results


def search_openalex(query: str, limit: int, email: str | None) -> list[dict]:
    params = {"search": query, "per-page": str(max(1, min(limit, 50)))}
    if email:
        params["mailto"] = email
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    results: list[dict] = []
    for work in (data.get("results") or [])[:limit]:
        title = work.get("title") or ""
        abstract = ""
        inverted = work.get("abstract_inverted_index") or {}
        if isinstance(inverted, dict):
            pos = []
            for word, indices in inverted.items():
                if isinstance(indices, list):
                    for idx in indices:
                        pos.append((idx, word))
            pos.sort(key=lambda x: x[0])
            abstract = " ".join(w for _, w in pos)
        authors = [
            (a.get("author") or {}).get("display_name") or ""
            for a in (work.get("authorships") or [])
        ]
        results.append({
            "title": title,
            "abstract": abstract,
            "authors": [a for a in authors if a],
            "url": work.get("doi") and f"https://doi.org/{work['doi']}" or work.get("id") or "",
            "pdf_url": (work.get("open_access") or {}).get("oa_url") or "",
            "published": work.get("publication_date") or work.get("publication_year") and str(work["publication_year"]) or "",
            "source_type": "paper",
            "provider": "openalex",
            "score": float(safe_get(work, "relevance_score", default=0) or 0),
            "citations": int(work.get("cited_by_count") or 0),
        })
    return results


def search_semantic_scholar(query: str, limit: int, api_key: str | None) -> list[dict]:
    params = urllib.parse.urlencode({
        "query": query,
        "limit": str(max(1, min(limit, 100))),
        "fields": "title,abstract,authors,url,externalIds,year,citationCount,publicationTypes",
    })
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    data = http_get_json(url, headers=headers)
    results: list[dict] = []
    for paper in (data.get("data") or [])[:limit]:
        title = paper.get("title") or ""
        authors = [a.get("name") or "" for a in (paper.get("authors") or [])]
        ext = paper.get("externalIds") or {}
        results.append({
            "title": title,
            "abstract": paper.get("abstract") or "",
            "authors": [a for a in authors if a],
            "url": paper.get("url") or (ext.get("DOI") and f"https://doi.org/{ext['DOI']}") or "",
            "pdf_url": "",
            "published": str(paper.get("year") or ""),
            "source_type": "paper",
            "provider": "semantic_scholar",
            "score": 0.0,
            "citations": int(paper.get("citationCount") or 0),
        })
    return results


def search_tavily(query: str, limit: int, api_key: str) -> list[dict]:
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max(1, min(limit, 20)),
        "include_answer": False,
        "include_raw_content": False,
    }
    data = http_post_json("https://api.tavily.com/search", payload)
    results: list[dict] = []
    for item in (data.get("results") or [])[:limit]:
        results.append({
            "title": item.get("title") or "",
            "abstract": item.get("content") or "",
            "authors": [],
            "url": item.get("url") or "",
            "pdf_url": "",
            "published": "",
            "source_type": "web",
            "provider": "tavily",
            "score": float(item.get("score") or 0.0),
        })
    return results


def collect_local_literature(paths: list[str]) -> list[dict]:
    results: list[dict] = []
    for pattern in paths:
        p = Path(pattern)
        if not p.exists():
            continue
        if p.is_dir():
            files = sorted(p.rglob("*"))
        else:
            files = [p]
        for f in files:
            if not f.is_file():
                continue
            if f.suffix.lower() not in {".pdf", ".md", ".txt", ".json"}:
                continue
            results.append({
                "title": f.name,
                "abstract": "",
                "authors": [],
                "url": str(f.resolve()),
                "pdf_url": str(f.resolve()) if f.suffix.lower() == ".pdf" else "",
                "published": "",
                "source_type": "local_literature",
                "provider": "local_literature",
                "score": 0.0,
            })
    return results


def dedupe_sources(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = norm_title(item.get("title") or "") or item.get("url") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_queries(goals: list[dict], max_queries: int) -> list[tuple[str, str]]:
    """Return list of (goal_id, query) pairs."""
    pairs: list[tuple[str, str]] = []
    for goal in goals:
        goal_id = goal.get("goal_id") or "G0"
        title = goal.get("title") or ""
        req = goal.get("requirement") or goal.get("task") or ""
        base_queries = [title]
        if req and req != title:
            base_queries.append(req)
        for q in base_queries[: max(1, max_queries)]:
            pairs.append((goal_id, q.strip()))
    return pairs


def run_retrieval(config: dict, queries: list[str], goal_id: str) -> list[dict]:
    retrieval = config.get("retrieval") or {}
    enabled = set(retrieval.get("enabled_sources") or [])
    providers = retrieval.get("providers") or {}
    limits = retrieval.get("limits") or {}
    exclusions = retrieval.get("exclusions") or {}
    per_query = int(limits.get("max_results_per_query", 10))
    blocked_titles = exclusions.get("blocked_titles") or []
    blocked_domains = exclusions.get("blocked_domains") or []

    all_items: list[dict] = []
    for query in queries:
        if not query:
            continue
        if "arxiv" in enabled and (providers.get("arxiv") or {}).get("enabled", True):
            try:
                all_items.extend(search_arxiv(query, per_query))
            except Exception as exc:
                print(f"[WARN] arxiv failed for {query[:60]}: {exc}", file=sys.stderr)
        if "openalex" in enabled and (providers.get("openalex") or {}).get("enabled", True):
            email = get_env((providers.get("openalex") or {}).get("email_env"))
            try:
                all_items.extend(search_openalex(query, per_query, email))
            except Exception as exc:
                print(f"[WARN] openalex failed for {query[:60]}: {exc}", file=sys.stderr)
        if "semantic_scholar" in enabled and (providers.get("semantic_scholar") or {}).get("enabled", True):
            api_key = get_env((providers.get("semantic_scholar") or {}).get("api_key_env"))
            try:
                all_items.extend(search_semantic_scholar(query, per_query, api_key))
            except Exception as exc:
                print(f"[WARN] semantic_scholar failed for {query[:60]}: {exc}", file=sys.stderr)
        if "tavily" in enabled and (providers.get("tavily") or {}).get("enabled", False):
            api_key = get_env((providers.get("tavily") or {}).get("api_key_env"))
            if api_key:
                try:
                    all_items.extend(search_tavily(query, per_query, api_key))
                except Exception as exc:
                    print(f"[WARN] tavily failed for {query[:60]}: {exc}", file=sys.stderr)
        if "local_literature" in enabled:
            local_paths = exclusions.get("excluded_paths") or []
            if local_paths:
                all_items.extend(collect_local_literature(local_paths))

    filtered = [
        item for item in all_items
        if not is_blocked(item.get("title", ""), blocked_titles, blocked_domains, item.get("url"))
    ]
    deduped = dedupe_sources(filtered)
    for item in deduped:
        item["used_for_goal_ids"] = sorted(set(item.get("used_for_goal_ids") or []) | {goal_id})
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser(description="Run literature retrieval for AutoSciRub grounding.")
    parser.add_argument("--config", help="Path to sources YAML config or .autoscirub/config.yaml")
    parser.add_argument("--goals", help="Path to rubric_skeleton.json")
    parser.add_argument("--query", action="append", default=[], help="Direct query string (repeatable)")
    parser.add_argument("--goal-id", default="G0", help="Goal id for direct queries")
    parser.add_argument("--out", help="Output JSON path (default: .autoscirub/literature_sources.json)")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    state_dir = Path(config.get("state_dir", ".autoscirub"))

    goals: list[dict] = []
    if args.goals:
        skeleton = json.loads(Path(args.goals).read_text(encoding="utf-8"))
        goals = skeleton.get("goals") or []
    elif args.query:
        goals = [{"goal_id": args.goal_id, "title": args.query[0], "requirement": " ".join(args.query)}]
    else:
        parser.error("Provide --goals or at least one --query")

    max_queries = int((config.get("retrieval") or {}).get("limits", {}).get("max_queries_per_goal", 5))
    query_pairs = build_queries(goals, max_queries)

    goal_sources: dict[str, list[dict]] = {}
    all_sources: list[dict] = []
    title_to_source: dict[str, dict] = {}

    for goal_id, query in query_pairs:
        items = run_retrieval(config, [query], goal_id)
        goal_sources.setdefault(goal_id, []).extend(items)
        for item in items:
            key = norm_title(item.get("title") or "")
            if key in title_to_source:
                existing = title_to_source[key]
                existing["used_for_goal_ids"] = sorted(set(existing.get("used_for_goal_ids") or []) | {goal_id})
            else:
                title_to_source[key] = item
                all_sources.append(item)

    core_limit = int((config.get("retrieval") or {}).get("limits", {}).get("max_core_sources", 7))
    core_sources = all_sources[:core_limit]
    supplemental = all_sources[core_limit:core_limit + int((config.get("retrieval") or {}).get("limits", {}).get("max_supplemental_sources", 10))]

    output = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_used": {
            "state_dir": config.get("state_dir"),
            "enabled_sources": (config.get("retrieval") or {}).get("enabled_sources"),
            "limits": (config.get("retrieval") or {}).get("limits"),
        },
        "goals": [
            {
                "goal_id": g.get("goal_id"),
                "title": g.get("title"),
                "queries": [q for gid, q in query_pairs if gid == g.get("goal_id")],
            }
            for g in goals
        ],
        "core_sources": core_sources,
        "supplemental_sources": supplemental,
        "all_sources": all_sources,
    }

    out_path = Path(args.out) if args.out else state_dir / "literature_sources.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(all_sources)} sources to {out_path}")


if __name__ == "__main__":
    main()
