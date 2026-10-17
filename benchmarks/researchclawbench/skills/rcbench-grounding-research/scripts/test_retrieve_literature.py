#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("retrieve_literature.py")
SPEC = importlib.util.spec_from_file_location("retrieve_literature", SCRIPT)
assert SPEC and SPEC.loader
retrieval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retrieval)


class RetrievalTests(unittest.TestCase):
    def test_doi_extracted_from_publisher_pdf_url(self) -> None:
        self.assertEqual(
            retrieval.normalize_doi("https://example.test/doi/10.3847/1538-4365/aa96b0/pdf"),
            "10.3847/1538-4365/aa96b0",
        )
        self.assertEqual(
            retrieval.normalize_doi(
                "https://academic.oup.com/mnras/advance-article-pdf/doi/10.1093/mnras/staf1055/63615820/staf1055.pdf"
            ),
            "10.1093/mnras/staf1055",
        )

    def test_repository_identifier_is_not_mistaken_for_legacy_arxiv(self) -> None:
        self.assertEqual(
            retrieval.normalize_arxiv_id(
                "https://esploro.umontpellier.fr/esploro/outputs/preprint/Impact-of-ACT-DR6-and-DESI/99155650309311"
            ),
            "",
        )
        self.assertEqual(retrieval.normalize_arxiv_id("https://arxiv.org/abs/2505.08051v2"), "2505.08051")

    def test_query_plan_is_small_and_deduplicated(self) -> None:
        queries = retrieval.normalize_queries(
            [
                "method dataset metric",
                {"query": "method dataset metric", "priority": 9},
                {
                    "query_id": "q03",
                    "stage": "followup",
                    "query": "distinctive figure caption",
                    "target_signal": "missing artifact",
                    "priority": 2,
                },
            ],
            max_queries=2,
        )
        self.assertEqual([query["query"] for query in queries], ["method dataset metric", "distinctive figure caption"])
        self.assertEqual(queries[1]["stage"], "followup")

    def test_excess_queries_are_rejected_instead_of_truncated(self) -> None:
        with self.assertRaisesRegex(ValueError, "never truncated"):
            retrieval.normalize_queries(["first query", "second query", "third query"], 2)

    def test_cross_provider_dedup_keeps_hits(self) -> None:
        first = retrieval.make_paper(
            title="A Distinctive Scientific Result",
            provider="openalex",
            doi="https://doi.org/10.1234/Example.1",
            abstract="short",
        )
        second = retrieval.make_paper(
            title="A distinctive scientific result",
            provider="sciatlas",
            doi="10.1234/example.1",
            abstract="a longer abstract from the knowledge graph",
        )
        assert first and second
        first["_hit"] = {
            "hit_id": "q01-openalex:r1",
            "request_id": "q01-openalex",
            "query_id": "q01",
            "provider": "openalex",
            "provider_rank": 1,
            "provider_score": 0.8,
        }
        second["_hit"] = {
            "hit_id": "q01-sciatlas:r2",
            "request_id": "q01-sciatlas",
            "query_id": "q01",
            "provider": "sciatlas",
            "provider_rank": 2,
            "provider_score": 0.7,
        }
        papers, hit_map = retrieval.merge_papers([first, second], rrf_k=60)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["canonical_id"], "doi:10.1234/example.1")
        self.assertEqual(papers[0]["providers"], ["openalex", "sciatlas"])
        self.assertEqual(len(papers[0]["retrieval_hits"]), 2)
        self.assertIn("longer abstract", papers[0]["abstract"])
        self.assertEqual(set(hit_map.values()), {"doi:10.1234/example.1"})

    def test_sciatlas_known_response_path(self) -> None:
        response = {
            "request_id": "request-1",
            "result": {
                "sources": {
                    "kg": {
                        "papers": [
                            {"paper_id": "p1", "title": "Paper One", "year": 2026},
                            {"paper_id": "p2", "title": "Paper Two", "year": 2025},
                        ]
                    }
                }
            },
        }
        papers = retrieval.find_sciatlas_papers(response)
        self.assertEqual([paper["title"] for paper in papers], ["Paper One", "Paper Two"])

    def test_sciatlas_selects_discriminative_queries_not_first_two(self) -> None:
        queries = retrieval.normalize_queries(
            [
                {
                    "query_id": "q01",
                    "query": "single cell feature selection biological trajectories",
                    "key_terms": ["single cell", "feature selection", "biological trajectories"],
                    "priority": 1,
                },
                {
                    "query_id": "q02",
                    "query": "RPE iterative immunofluorescence trajectory",
                    "key_terms": ["RPE", "iterative immunofluorescence", "trajectory"],
                    "priority": 2,
                },
                {
                    "query_id": "q03",
                    "query": "DELVE single cell dynamic modules",
                    "key_terms": ["DELVE", "single cell", "dynamic modules"],
                    "priority": 3,
                },
            ],
            4,
        )
        selected = retrieval.select_provider_queries("sciatlas", queries, 2)
        self.assertEqual({query["query_id"] for query in selected}, {"q02", "q03"})

    def test_sciatlas_resume_prioritizes_citation_followup(self) -> None:
        queries = retrieval.normalize_queries(
            [
                {"query_id": "q01", "query": "broad materials discovery", "priority": 1},
                {"query_id": "q02", "query": "crystal neural network", "priority": 2},
                {
                    "query_id": "q04",
                    "stage": "followup",
                    "query": '"Crystal Graph Convolutional Neural Networks" formation energy',
                    "key_terms": ["Crystal Graph Convolutional Neural Networks", "formation energy"],
                    "priority": 4,
                    "parent_query_id": "q02",
                },
            ],
            4,
        )
        selected = retrieval.select_provider_queries("sciatlas", queries, 2)
        self.assertIn("q04", [query["query_id"] for query in selected])
        self.assertGreater(
            retrieval.sciatlas_query_score(next(query for query in queries if query["query_id"] == "q04")),
            retrieval.sciatlas_query_score(next(query for query in queries if query["query_id"] == "q01")),
        )

    def test_sciatlas_does_not_prefer_an_acronym_soup_over_exact_method(self) -> None:
        queries = retrieval.normalize_queries(
            [
                {
                    "query_id": "q01",
                    "query": '"Local Distance Network" Hubble constant 73.50 0.81 covariance',
                    "target_signal": "Exact method and numerical result",
                    "key_terms": ["Local Distance Network", "73.50", "0.81", "covariance"],
                    "priority": 1,
                },
                {
                    "query_id": "q03",
                    "query": "Cepheids TRGB Miras JAGB SBF SNe II FP TF covariance network H0 consensus",
                    "target_signal": "Full indicator network and artifact signatures",
                    "key_terms": ["Cepheids", "TRGB", "Miras", "JAGB", "SBF", "SNe II", "FP", "TF"],
                    "priority": 3,
                },
            ],
            4,
        )
        selected = retrieval.select_provider_queries("sciatlas", queries, 1)
        self.assertEqual(selected[0]["query_id"], "q01")

    def test_provider_budget_and_trace_mapping(self) -> None:
        calls: list[str] = []

        def fake_search(query: str, limit: int, config: dict) -> tuple[list[dict], dict]:
            calls.append(query)
            paper = retrieval.make_paper(
                title=f"Result for {query}",
                provider="fake",
                url=f"https://example.test/{len(calls)}",
                score=1.0,
            )
            return ([paper] if paper else []), {"request_id": f"fake-{len(calls)}"}

        old = retrieval.PROVIDER_FUNCTIONS.get("fake")
        retrieval.PROVIDER_FUNCTIONS["fake"] = fake_search
        try:
            config = {
                "retrieval": {
                    "enabled_sources": ["fake"],
                    "providers": {"fake": {"enabled": True, "max_queries": 2, "max_results": 3}},
                    "limits": {"max_results_per_query": 3, "max_core_sources": 5, "rrf_k": 60},
                }
            }
            queries = retrieval.normalize_queries(["query one", "query two", "query three"], 4)
            candidates, trace = retrieval.run(
                config=config,
                queries=queries,
                task_id="TEST",
                provider_override=None,
                local_paths=[],
            )
        finally:
            if old is None:
                retrieval.PROVIDER_FUNCTIONS.pop("fake", None)
            else:
                retrieval.PROVIDER_FUNCTIONS["fake"] = old
        self.assertEqual(calls, ["query one", "query two"])
        self.assertEqual(trace["summary"]["attempt_count"], 2)
        self.assertEqual(len(candidates["all_sources"]), 2)
        self.assertEqual(trace["attempts"][0]["results"][0]["canonical_id"], candidates["all_sources"][0]["canonical_id"])

    def test_resume_runs_only_new_query(self) -> None:
        calls: list[str] = []

        def fake_search(query: str, limit: int, config: dict) -> tuple[list[dict], dict]:
            calls.append(query)
            paper = retrieval.make_paper(
                title=f"Paper for {query}", provider="fake", url=f"https://example.test/{query.replace(' ', '-')}"
            )
            return ([paper] if paper else []), {}

        old = retrieval.PROVIDER_FUNCTIONS.get("fake")
        retrieval.PROVIDER_FUNCTIONS["fake"] = fake_search
        config = {
            "retrieval": {
                "enabled_sources": ["fake"],
                "providers": {"fake": {"enabled": True, "max_queries": 2, "max_results": 2}},
                "limits": {"max_results_per_query": 2, "max_core_sources": 5, "rrf_k": 60},
            }
        }
        try:
            first_queries = retrieval.normalize_queries(["first query"], 4)
            first_candidates, first_trace = retrieval.run(
                config=config,
                queries=first_queries,
                task_id="TEST",
                provider_override=None,
                local_paths=[],
            )
            resumed_queries = retrieval.normalize_queries([*first_queries, "followup query"], 4)
            resumed_candidates, resumed_trace = retrieval.run(
                config=config,
                queries=resumed_queries,
                task_id="TEST",
                provider_override=None,
                local_paths=[],
                existing_candidates=first_candidates,
                existing_trace=first_trace,
            )
        finally:
            if old is None:
                retrieval.PROVIDER_FUNCTIONS.pop("fake", None)
            else:
                retrieval.PROVIDER_FUNCTIONS["fake"] = old
        self.assertEqual(calls, ["first query", "followup query"])
        self.assertEqual(resumed_trace["summary"]["attempt_count"], 2)
        self.assertEqual(len(resumed_candidates["all_sources"]), 2)


if __name__ == "__main__":
    unittest.main()
