#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("annotate_retrieval_trace.py")
SPEC = importlib.util.spec_from_file_location("annotate_retrieval_trace", SCRIPT)
assert SPEC and SPEC.loader
annotator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(annotator)


class AnnotationTests(unittest.TestCase):
    def test_query_metrics_receive_grounding_labels(self) -> None:
        trace = {
            "papers": [
                {
                    "canonical_id": "doi:10.1/example",
                    "title": "Exact Source Paper",
                    "retrieval_hits": [
                        {"query_id": "q01", "provider": "openalex", "provider_rank": 3},
                        {"query_id": "q02", "provider": "sciatlas", "provider_rank": 1},
                    ],
                }
            ],
            "query_metrics": [{"query_id": "q01"}, {"query_id": "q02"}, {"query_id": "q03"}],
        }
        grounding = {
            "candidates": [{"title": "Exact Source Paper", "target_like_candidate": "possible"}],
            "paper_identity_gate": {"pass": True},
        }
        result = annotator.annotate(trace, grounding)
        self.assertTrue(result["query_metrics"][0]["possible_hit"])
        self.assertEqual(result["query_metrics"][0]["best_final_candidate_provider_rank"], 3)
        self.assertEqual(result["query_metrics"][1]["best_final_candidate_provider_rank"], 1)
        self.assertFalse(result["query_metrics"][2]["final_candidate_hit"])
        self.assertTrue(result["grounding_evaluation"]["identity_gate_pass"])

    def test_arxiv_url_matches_when_title_format_differs(self) -> None:
        trace = {
            "papers": [
                {
                    "canonical_id": "arxiv:2505.08051",
                    "title": "A Title with <i>Markup</i>",
                    "retrieval_hits": [{"query_id": "q01", "provider_rank": 2}],
                }
            ],
            "query_metrics": [{"query_id": "q01"}],
        }
        grounding = {
            "candidates": [
                {
                    "title": "A differently formatted title",
                    "url_or_path": "https://arxiv.org/abs/2505.08051v2",
                    "target_like_candidate": "weak",
                }
            ]
        }
        result = annotator.annotate(trace, grounding)
        self.assertTrue(result["query_metrics"][0]["final_candidate_hit"])
        self.assertFalse(result["query_metrics"][0]["possible_hit"])


if __name__ == "__main__":
    unittest.main()
