#!/usr/bin/env python3
"""Retrieve literature; paths are relative to the selected research project."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "state_dir": ".autoscirub",
    "workflow": {
        "max_revision_rounds": 1
    },
    "retrieval": {
        "enabled_sources": [
            "local_literature",
            "arxiv",
            "openalex",
            "semantic_scholar"
        ],
        "local_literature": {
            "paths": []
        },
        "providers": {
            "arxiv": {
                "enabled": True
            },
            "openalex": {
                "enabled": True,
                "email_env": "OPENALEX_EMAIL",
                "api_key_env": "OPENALEX_API_KEY"
            },
            "semantic_scholar": {
                "enabled": True,
                "api_key_env": "SEMANTIC_SCHOLAR_API_KEY"
            },
            "tavily": {
                "enabled": False,
                "api_key_env": "TAVILY_API_KEY"
            },
            "mineru": {
                "enabled": False,
                "api_key_env": "MINERU_API_TOKEN"
            }
        },
        "limits": {
            "max_queries_per_goal": 5,
            "max_core_sources": 7,
            "max_supplemental_sources": 10,
            "max_results_per_query": 10
        },
        "exclusions": {
            "excluded_paths": [],
            "blocked_titles": [],
            "blocked_domains": []
        }
    }
}


class ConfigError(ValueError):
    """Invalid configuration or a missing runtime dependency."""


def dependencies():
    try:
        import yaml
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ConfigError(
            'Missing Python dependencies. In your active Python environment run: '
            'python -m pip install "PyYAML>=6,<7" "jsonschema>=4.18,<5"'
        ) from exc
    return yaml, Draft202012Validator


def read_yaml(text: str) -> dict:
    """Use one YAML implementation; reject duplicate keys rather than overwrite."""
    yaml, _ = dependencies()

    class UniqueLoader(yaml.SafeLoader):
        pass

    def unique_mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ConfigError(f"Line {key_node.start_mark.line + 1}: configuration keys must be strings")
            if key in seen:
                raise ConfigError(f"Line {key_node.start_mark.line + 1}: duplicate key {key!r}")
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
    try:
        data = yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ConfigError(f"Invalid YAML{location}: {getattr(exc, 'problem', 'check YAML syntax')}") from exc
    # An empty file is almost always an accidental/incomplete configuration.
    if not isinstance(data, dict):
        raise ConfigError("Configuration must be a YAML mapping; use {} for defaults")
    return data


def try_load_yaml(path: Path) -> dict:
    try:
        return read_yaml(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"Cannot read configuration {path}: {exc}") from exc


def deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_config(config: dict) -> dict:
    """Validate overrides and resolved configs using the exact same schema."""
    _, validator = dependencies()
    schema_path = Path(__file__).resolve().parent.parent / "references/config.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(validator(schema).iter_errors(config), key=lambda e: str(list(e.path)))
    if errors:
        details = []
        for error in errors[:5]:
            field = ".".join(str(item) for item in error.absolute_path) or "config"
            # Do not print values: users sometimes accidentally paste keys into config.
            if error.validator == "additionalProperties":
                allowed = error.schema.get("properties", {})
                unknown = sorted(set(error.instance) - set(allowed))
                details.append(f"{field}: unknown field(s) {', '.join(unknown)}")
            elif error.validator == "enum":
                details.append(f"{field}: choose one of {', '.join(error.schema['enum'])}")
            else:
                details.append(f"{field}: expected {error.schema.get('type', 'valid value')} "
                               f"({error.validator}: {error.validator_value})")
        raise ConfigError("; ".join(details))
    return config


def discover_config(project: Path, explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()
    candidate = project / ".autoscirub/config.yaml"
    return candidate if candidate.exists() else None


def load_config(config_path: Path | None = None, *, project: Path | None = None,
                state_dir: str | None = None) -> dict:
    project = (project or Path.cwd()).expanduser().resolve()
    selected = discover_config(project, config_path)
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if selected is not None:
        if not selected.is_file():
            raise ConfigError(f"Configuration file not found: {selected}")
        override = validate_config(try_load_yaml(selected))
        config = deep_merge(config, override)
    chosen_state = state_dir if state_dir is not None else os.environ.get("AUTOSCIRUB_STATE_DIR")
    if chosen_state is not None:
        config["state_dir"] = chosen_state
    validate_config(config)
    # JSON Schema considers 5.0 an integer; normalize before Python slicing.
    config["retrieval"]["limits"] = {key: int(value) for key, value in config["retrieval"]["limits"].items()}
    config["workflow"]["max_revision_rounds"] = int(config["workflow"]["max_revision_rounds"])
    config["state_dir"] = str((project / Path(config["state_dir"]).expanduser()).resolve())
    return config


def write_json(path: Path, data: dict) -> None:
    """Publish complete JSON atomically; interrupted writes keep the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temp_name = stream.name
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()


def get_env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name, "").strip()
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
            if domain and (host == domain.lower().lstrip(".") or host.endswith("." + domain.lower().lstrip("."))):
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
    url = f"https://export.arxiv.org/api/query?{params}"
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


def search_openalex(query: str, limit: int, email: str | None, api_key: str | None = None) -> list[dict]:
    params = {"search": query, "per-page": str(max(1, min(limit, 50)))}
    if email:
        params["mailto"] = email
    if api_key:
        params["api_key"] = api_key
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
            "url": work.get("doi") and (work["doi"] if work["doi"].startswith("https://doi.org/") else f"https://doi.org/{work['doi']}") or work.get("id") or "",
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


def collect_local_literature(paths: list[str], excluded_paths: list[str] | None = None,
                             project: Path | None = None) -> list[dict]:
    """Index local documents once. Prune exclusions before entering directories."""
    project = (project or Path.cwd()).resolve()
    excluded = [(project / Path(p).expanduser()).resolve() for p in excluded_paths or []]

    def blocked(path: Path) -> bool:
        real = path.resolve()
        return any(real == root or root in real.parents for root in excluded)

    results = []
    seen = set()
    def scan_error(error):
        raise error

    for name in paths:
        source = project / Path(name).expanduser()
        if blocked(source):
            continue
        if not source.exists():
            raise FileNotFoundError(f"Local literature path does not exist: {source}")
        if source.is_dir():
            files = []
            for directory, dirs, names in os.walk(source, followlinks=False, onerror=scan_error):
                dirs[:] = sorted(d for d in dirs if not blocked(Path(directory) / d)
                                 and not (Path(directory) / d).is_symlink())
                files.extend(Path(directory) / n for n in sorted(names))
        else:
            files = [source]
        for path in files:
            if blocked(path) or not path.is_file() or path.suffix.lower() not in {".pdf", ".md", ".txt", ".json"}:
                continue
            real = path.resolve()
            if real in seen:
                continue
            seen.add(real)
            results.append({
                "title": path.name, "abstract": "", "authors": [], "url": str(real),
                "pdf_url": str(real) if path.suffix.lower() == ".pdf" else "",
                "published": "", "source_type": "local_literature",
                "provider": "local_literature", "score": 0.0,
            })
    return results


def source_key(item: dict) -> str:
    # Same filenames in different directories are not duplicate local papers.
    if item.get("provider") == "local_literature":
        return item.get("url", "")
    return norm_title(item.get("title", "")) or item.get("url", "")


def dedupe_sources(items: list[dict]) -> list[dict]:
    found = {}
    for item in items:
        key = source_key(item)
        if not key:
            continue
        if key not in found:
            found[key] = dict(item)
        found[key]["used_for_goal_ids"] = sorted(
            set(found[key].get("used_for_goal_ids", [])) | set(item.get("used_for_goal_ids", [])))
    return list(found.values())


def build_queries(goals: list[dict], max_queries: int) -> list[tuple[str, str]]:
    pairs = []
    for i, goal in enumerate(goals):
        goal_id = goal.get("goal_id") or f"G{i + 1}"
        queries = goal.get("queries", [goal.get("title", ""), goal.get("requirement", goal.get("task", ""))])
        if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
            raise ConfigError(f"Goal {goal_id}: queries must be a list of strings")
        for query in list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:max_queries]:
            pairs.append((goal_id, query))
    return pairs


def failure_reason(exc: Exception) -> str:
    """Avoid recording provider response bodies or URLs that can contain keys."""
    if isinstance(exc, FileNotFoundError):
        return "Local literature path missing; check retrieval.local_literature.paths."
    chain = exc
    for _ in range(8):
        if isinstance(chain, urllib.error.HTTPError):
            if chain.code in (401, 403):
                return f"HTTP {chain.code}: check API key and provider access."
            if chain.code == 429:
                return "HTTP 429: provider rate limit; retry later or configure an API key."
            return f"HTTP {chain.code}: provider request failed."
        if isinstance(chain, (TimeoutError, urllib.error.URLError)):
            return "Network request failed or timed out; check connection/proxy and retry."
        if chain.__cause__ is None:
            break
        chain = chain.__cause__
    return f"{type(exc).__name__}: provider failed; check configuration or retry later."


def retrieve(config: dict, pairs: list[tuple[str, str]], project: Path) -> tuple[list[dict], list[dict]]:
    retrieval = config["retrieval"]
    providers = retrieval["providers"]
    limits = retrieval["limits"]
    exclusions = retrieval["exclusions"]
    trace = []
    items = []

    def record(provider, goal_id, query, operation=None, reason=None):
        event = {"provider": provider, "goal_id": goal_id, "query": query}
        started = time.monotonic()
        if operation is None:
            event.update(status="skipped", reason=reason, count=0)
        else:
            print(f"[retrieval] {provider}: {query or 'indexing local documents'}", file=sys.stderr, flush=True)
            try:
                results = operation()
                filtered = [item for item in results if not is_blocked(
                    item.get("title", ""), exclusions["blocked_titles"],
                    exclusions["blocked_domains"], item.get("url"))]
                for item in filtered:
                    item["used_for_goal_ids"] = [goal_id] if goal_id else sorted({g for g, _ in pairs})
                items.extend(filtered)
                event.update(status="ok" if filtered else "empty", count=len(filtered))
            except Exception as exc:
                event.update(status="failed", count=0, reason=failure_reason(exc))
        event["duration_seconds"] = round(time.monotonic() - started, 3)
        trace.append(event)
        print(f"[{event['status']}] {provider}: {event.get('reason', str(event['count']) + ' sources')}",
              file=sys.stderr, flush=True)

    for name in retrieval["enabled_sources"]:
        if name == "web":
            record(name, None, None, reason="Use the agent's native web search; this script does not implement it.")
        elif name == "local_literature":
            paths = retrieval["local_literature"]["paths"]
            if paths:
                record(name, None, None, lambda: collect_local_literature(paths, exclusions["excluded_paths"], project))
            else:
                record(name, None, None, reason="No local paths configured; add retrieval.local_literature.paths.")
        else:
            provider = providers[name]
            if not provider.get("enabled", True):
                record(name, None, None, reason="Disabled in configuration.")
                continue
            key = get_env(provider.get("api_key_env"))
            if name == "tavily" and not key:
                record(name, None, None, reason=f"Set {provider.get('api_key_env', 'TAVILY_API_KEY')} to enable Tavily.")
                continue
            for goal_id, query in pairs:
                per_query = limits["max_results_per_query"]
                operations = {
                    "arxiv": lambda: search_arxiv(query, per_query),
                    "openalex": lambda: search_openalex(query, per_query, get_env(provider.get("email_env")), key),
                    "semantic_scholar": lambda: search_semantic_scholar(query, per_query, key),
                    "tavily": lambda: search_tavily(query, per_query, key),
                }
                record(name, goal_id, query, operations[name])
    return dedupe_sources(items), trace


def retrieval_status(trace: list[dict]) -> str:
    successful = any(e["status"] in {"ok", "empty"} for e in trace)
    failed = any(e["status"] == "failed" for e in trace)
    if not successful:
        return "failed" if failed else "unavailable"
    if failed:
        return "partial"
    return "ok" if any(e["count"] for e in trace) else "empty"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Research project root (default: current directory)")
    parser.add_argument("--config", type=Path, help="Explicit YAML file; otherwise read PROJECT/.autoscirub/config.yaml")
    parser.add_argument("--state-dir", help="Override AUTOSCIRUB_STATE_DIR and config state_dir")
    parser.add_argument("--goals", help="Rubric skeleton path, relative to project")
    parser.add_argument("--query", action="append", default=[], help="Direct query (repeatable, kept separate)")
    parser.add_argument("--goal-id", default="G0")
    parser.add_argument("--out", help="Output path relative to project (default: STATE/literature_sources.json)")
    parser.add_argument("--validate-config", action="store_true", help="Check configuration without network requests")
    args = parser.parse_args(argv)
    project = args.project.expanduser().resolve()
    try:
        if not project.is_dir():
            raise ConfigError(f"Project directory not found: {project}")
        config = load_config(args.config, project=project, state_dir=args.state_dir)
        chosen = discover_config(project, args.config)
        print(f"Config: {chosen or 'built-in defaults'}; state: {config['state_dir']}", file=sys.stderr)
        if args.validate_config:
            print("configuration valid")
            return 0
        if args.goals and args.query:
            raise ConfigError("Use --goals or --query, not both")
        if args.goals:
            skeleton = json.loads((project / args.goals).read_text(encoding="utf-8"))
            goals = skeleton.get("goals") if isinstance(skeleton, dict) else None
        elif args.query:
            goals = [{"goal_id": args.goal_id, "queries": args.query}]
        else:
            raise ConfigError("Provide --goals or at least one --query")
        if not isinstance(goals, list) or not goals or not all(isinstance(g, dict) for g in goals):
            raise ConfigError("Rubric skeleton must contain a non-empty goals list")
        for goal in goals:
            for field in ("goal_id", "title", "requirement", "task"):
                if field in goal and not isinstance(goal[field], str):
                    raise ConfigError(f"Goal {field} must be a string")
        pairs = build_queries(goals, config["retrieval"]["limits"]["max_queries_per_goal"])
        if not pairs:
            raise ConfigError("Goals contain no non-empty search queries")
        sources, trace = retrieve(config, pairs, project)
        status = retrieval_status(trace)
        limits = config["retrieval"]["limits"]
        core = limits["max_core_sources"]
        output = {
            "schema_version": "1.1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": status, "provider_results": trace,
            "config_used": {"config_path": str(chosen) if chosen else None,
                            "project": str(project), "state_dir": config["state_dir"],
                            "enabled_sources": config["retrieval"]["enabled_sources"], "limits": limits},
            "goals": [{"goal_id": g, "queries": [q for gid, q in pairs if gid == g]}
                      for g in dict.fromkeys(g for g, _ in pairs)],
            "core_sources": sources[:core],
            "supplemental_sources": sources[core:core + limits["max_supplemental_sources"]],
            "all_sources": sources,
        }
        out = project / args.out if args.out else Path(config["state_dir"]) / "literature_sources.json"
        # Failure diagnostics must not overwrite a previously useful source index.
        if status in {"failed", "unavailable"}:
            diagnostic = out.with_name(out.stem + ".failure.json")
            write_json(diagnostic, output)
            print(f"Retrieval {status}; inspect {diagnostic}. Previous results preserved.", file=sys.stderr)
            return 3
        write_json(out, output)
        print(f"Retrieval {status}: wrote {len(sources)} sources to {out}")
        if status == "empty":
            print("Queries completed but found no usable sources. Try broader terms or local papers.", file=sys.stderr)
        return 0
    except (ConfigError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
