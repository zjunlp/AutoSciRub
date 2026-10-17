#!/usr/bin/env python3
"""Annotate mechanical retrieval metrics with final grounding decisions."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def normalize_title(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def canonical_id_from_text(value: Any) -> str:
    text = str(value or "")
    doi = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", text, flags=re.IGNORECASE)
    if doi:
        value = doi.group(0).rstrip(".,;)]}").lower()
        return f"doi:{value}"
    arxiv = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)(\d{4}\.\d{4,5})", text, flags=re.IGNORECASE)
    if arxiv:
        return f"arxiv:{arxiv.group(1).lower()}"
    return ""


def annotate(trace: dict[str, Any], grounding: dict[str, Any]) -> dict[str, Any]:
    title_to_paper = {
        normalize_title(paper.get("title")): paper
        for paper in trace.get("papers") or []
        if normalize_title(paper.get("title"))
    }
    canonical_to_paper = {
        paper.get("canonical_id"): paper
        for paper in trace.get("papers") or []
        if paper.get("canonical_id")
    }
    retained_ids: set[str] = set()
    possible_ids: set[str] = set()
    unmatched: list[str] = []

    for candidate in grounding.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        title = str(candidate.get("title") or "").strip()
        candidate_id = canonical_id_from_text(candidate.get("url_or_path"))
        paper = canonical_to_paper.get(candidate_id) or title_to_paper.get(normalize_title(title))
        if paper is None:
            if title:
                unmatched.append(title)
            continue
        canonical_id = paper.get("canonical_id")
        if not canonical_id:
            continue
        retained_ids.add(canonical_id)
        if candidate.get("target_like_candidate") == "possible":
            possible_ids.add(canonical_id)

    query_to_papers: dict[str, set[str]] = {}
    query_to_ranks: dict[tuple[str, str], list[int]] = {}
    for paper in trace.get("papers") or []:
        canonical_id = paper.get("canonical_id")
        if not canonical_id:
            continue
        for hit in paper.get("retrieval_hits") or []:
            query_id = hit.get("query_id")
            if not query_id or query_id == "local":
                continue
            query_to_papers.setdefault(query_id, set()).add(canonical_id)
            query_to_ranks.setdefault((query_id, canonical_id), []).append(int(hit.get("provider_rank") or 10**9))

    for metric in trace.get("query_metrics") or []:
        query_id = metric.get("query_id")
        paper_ids = query_to_papers.get(query_id, set())
        final_hits = paper_ids & retained_ids
        possible_hits = paper_ids & possible_ids
        metric["final_candidate_hit"] = bool(final_hits)
        metric["possible_hit"] = bool(possible_hits)
        ranks = [
            min(query_to_ranks.get((query_id, paper_id), [10**9]))
            for paper_id in final_hits
        ]
        metric["best_final_candidate_provider_rank"] = min(ranks) if ranks else None
        metric["final_candidate_count"] = len(final_hits)
        metric["possible_candidate_count"] = len(possible_hits)

    trace["grounding_evaluation"] = {
        "retained_candidate_count": len(retained_ids),
        "possible_candidate_count": len(possible_ids),
        "unmatched_grounding_titles": unmatched,
        "identity_gate_pass": (grounding.get("paper_identity_gate") or {}).get("pass"),
    }
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description="Add grounding outcomes to retrieval_trace.json")
    parser.add_argument("--trace", default="outputs/retrieval_trace.json")
    parser.add_argument("--grounding", default="outputs/grounding_research.json")
    args = parser.parse_args()
    trace_path = Path(args.trace)
    grounding_path = Path(args.grounding)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    grounding = json.loads(grounding_path.read_text(encoding="utf-8"))
    annotate(trace, grounding)
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"annotated retrieval metrics in {trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
