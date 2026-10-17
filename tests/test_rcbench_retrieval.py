"""Offline adapter regressions: budgets, resume, input boundaries, and bundled tests."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "benchmarks/researchclawbench/skills"
SCRIPTS = SKILLS / "rcbench-grounding-research/scripts"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


retrieval = load_module("rcbench_retrieval", SCRIPTS / "retrieve_literature.py")
mineru = load_module("rcbench_mineru", SKILLS / "rcbench-mineru-pdf-to-markdown/scripts/mineru_pdf_to_markdown.py")


def config(provider="fake", max_queries=3):
    return {"retrieval": {"enabled_sources": [provider], "providers": {
        provider: {"enabled": True, "max_queries": max_queries, "max_results": 2}},
        "limits": {"max_queries_per_task": 5}}}


def fake_papers(query, limit, provider_config):
    return [retrieval.make_paper(title=f"Paper {query}", provider="fake",
                                url=f"https://example.test/{query}")], {}


class AdapterRetrievalTests(unittest.TestCase):
    def run_retrieval(self, cfg, queries, **kwargs):
        return retrieval.run(config=cfg, queries=queries, task_id="EXAMPLE", provider_override=None,
                             local_paths=[], **kwargs)

    def cli(self, workspace, extra):
        argv = ["retrieve_literature.py", "--config", str(workspace / "profile.yaml"),
                "--workspace", str(workspace), "--task-id", "EXAMPLE", *extra]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return retrieval.main()

    def write_config(self, workspace, value):
        # JSON is also valid YAML; avoid dependence on a serializer in fixtures.
        (workspace / "profile.yaml").write_text(json.dumps(value), encoding="utf-8")

    def test_generated_ids_remain_stable_when_queries_reorder(self):
        first = retrieval.normalize_queries(["alpha method", "beta method"], 2)
        reordered = retrieval.normalize_queries(["beta method", "alpha method"], 2)
        self.assertEqual({q["query"]: q["query_id"] for q in first},
                         {q["query"]: q["query_id"] for q in reordered})

    def test_id_collision_and_stage_reassignment_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "changed query text"):
            retrieval.normalize_queries([{"query_id": "q1", "query": "alpha"},
                                         {"query_id": "q1", "query": "beta"}], 3)
        with self.assertRaisesRegex(ValueError, "change stage"):
            retrieval.normalize_queries([{"query_id": "q1", "query": "alpha"},
                                         {"query_id": "q1", "query": "alpha", "stage": "followup"}], 3)

    def test_workflow_stage_limit_is_checked_before_any_provider_call(self):
        cfg = config()
        cfg["workflow"] = {"max_initial_queries": 1, "max_followup_queries": 0}
        queries = retrieval.normalize_queries(["alpha", "beta"], 5)
        with patch.dict(retrieval.PROVIDER_FUNCTIONS, {"fake": fake_papers}), \
                self.assertRaisesRegex(ValueError, "max_initial_queries"):
            self.run_retrieval(cfg, queries)

    def test_resume_rejects_changed_query_text_and_total_excess(self):
        cfg = config()
        cfg["retrieval"]["limits"]["max_queries_per_task"] = 1
        with patch.dict(retrieval.PROVIDER_FUNCTIONS, {"fake": fake_papers}):
            candidates, trace = self.run_retrieval(cfg, retrieval.normalize_queries(
                [{"query_id": "q1", "query": "alpha"}], 5))
            with self.assertRaisesRegex(ValueError, "changed query text"):
                self.run_retrieval(cfg, retrieval.normalize_queries(
                    [{"query_id": "q1", "query": "changed"}], 5),
                    existing_candidates=candidates, existing_trace=trace)
            with self.assertRaisesRegex(ValueError, "never truncated"):
                self.run_retrieval(cfg, retrieval.normalize_queries(["beta"], 5),
                    existing_candidates=candidates, existing_trace=trace)

    def test_sciatlas_budget_is_cumulative_and_increase_uses_new_queries(self):
        cfg = config("sciatlas", 2)
        calls = []

        def search(query, limit, provider_config):
            calls.append(query)
            return fake_papers(query, limit, provider_config)

        initial = retrieval.normalize_queries(["first method", "second method"], 5)
        followup = retrieval.normalize_queries([
            {"query": '"Exact Method"', "stage": "followup"}], 5)
        with patch.dict(retrieval.PROVIDER_FUNCTIONS, {"sciatlas": search}):
            candidates, trace = self.run_retrieval(cfg, initial)
            candidates, trace = self.run_retrieval(cfg, followup, existing_candidates=candidates, existing_trace=trace)
            self.assertEqual(len(calls), 2)
            self.assertEqual(trace["budget_usage"]["providers"]["sciatlas"]["remaining_before_run"], 0)
            cfg["retrieval"]["providers"]["sciatlas"]["max_queries"] = 3
            _, trace = self.run_retrieval(cfg, followup, existing_candidates=candidates, existing_trace=trace)
        self.assertEqual(calls, ["first method", "second method", '"Exact Method"'])
        self.assertEqual(trace["summary"]["attempt_count"], 3)

    def test_failure_preserves_outputs_and_resume_does_not_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            self.write_config(workspace, config())
            calls = []

            def search(query, limit, provider_config):
                calls.append(query)
                if query == "broken":
                    raise RuntimeError("simulated offline failure")
                return fake_papers(query, limit, provider_config)

            with patch.dict(retrieval.PROVIDER_FUNCTIONS, {"fake": search}):
                self.assertEqual(self.cli(workspace, ["--query", "working"]), 0)
                out = workspace / "outputs/literature_candidates.json"
                trace = workspace / "outputs/retrieval_trace.json"
                before = (out.read_bytes(), trace.read_bytes())
                self.assertEqual(self.cli(workspace, ["--resume", "--query", "broken"]), 1)
                self.assertEqual((out.read_bytes(), trace.read_bytes()), before)
                diagnostic = workspace / "outputs/retrieval_trace.failed.json"
                self.assertEqual(json.loads(diagnostic.read_text())["summary"]["failed_attempts"], 1)
                self.assertEqual(self.cli(workspace, ["--resume"]), 1)
                self.assertEqual((out.read_bytes(), trace.read_bytes()), before)
                self.assertEqual(calls, ["working", "broken"])
                self.assertEqual(self.cli(workspace, ["--resume", "--query", "recovered"]), 0)
                saved = json.loads(trace.read_text())
                self.assertEqual(saved["summary"]["attempt_count"], 3)
                self.assertEqual(saved["budget_usage"]["providers"]["fake"]["used_unique_attempts"], 3)

    def test_initial_failure_resume_uses_diagnostics_without_resetting_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            self.write_config(workspace, config(max_queries=1))
            search = unittest.mock.Mock(side_effect=RuntimeError("offline"))
            with patch.dict(retrieval.PROVIDER_FUNCTIONS, {"fake": search}):
                self.assertEqual(self.cli(workspace, ["--query", "first"]), 1)
                self.assertEqual(self.cli(workspace, ["--resume", "--query", "second"]), 1)
            self.assertEqual(search.call_count, 1)
            self.assertFalse((workspace / "outputs/literature_candidates.json").exists())

    def test_configured_local_only_retrieval_needs_no_query_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            related = workspace / "related_work"
            related.mkdir()
            (related / "paper.md").write_text("# Public source\n", encoding="utf-8")
            cfg = config("local_literature")
            cfg["retrieval"]["providers"]["local_literature"]["paths"] = ["related_work"]
            self.write_config(workspace, cfg)
            self.assertEqual(self.cli(workspace, []), 0)
            output = json.loads((workspace / "outputs/literature_candidates.json").read_text())
            self.assertEqual(output["all_sources"][0]["title"], "Public source")

    def test_local_scan_prunes_hidden_excluded_and_symlink_sources(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            workspace = Path(temp)
            for name in ("public", "target_study", "private"):
                (workspace / name).mkdir()
                (workspace / name / "paper.md").write_text(f"# {name}\n", encoding="utf-8")
            (workspace / "checklist.json").write_text("sensitive", encoding="utf-8")
            (Path(outside) / "paper.md").write_text("# outside", encoding="utf-8")
            (workspace / "public/hidden-link.md").symlink_to(workspace / "target_study/paper.md")
            (workspace / "public/escape.md").symlink_to(Path(outside) / "paper.md")
            (workspace / "public/hidden-dir").symlink_to(workspace / "target_study", target_is_directory=True)
            original_scandir = retrieval.os.scandir

            def guard_scandir(path):
                self.assertNotIn(Path(path).name, {"target_study", "private", "hidden-dir"})
                return original_scandir(path)

            with patch.object(retrieval.os, "scandir", side_effect=guard_scandir):
                papers = retrieval.collect_local_literature(["."], 50, workspace=workspace,
                                                            excluded_paths=["private"])
            self.assertEqual([paper["title"] for paper in papers], ["public"])
            for unsafe in ("target_study", "checklist.json", "public/hidden-link.md", "public/escape.md", "private"):
                with self.assertRaises(ValueError):
                    retrieval.collect_local_literature([unsafe], 5, workspace=workspace, excluded_paths=["private"])

    def test_disabled_local_provider_is_not_scanned(self):
        cfg = config("local_literature")
        cfg["retrieval"]["providers"]["local_literature"]["enabled"] = False
        with patch.object(retrieval, "collect_local_literature") as scan:
            self.run_retrieval(cfg, [])
        scan.assert_not_called()

    def test_mineru_blocks_hidden_paths_before_fingerprinting_or_network(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            workspace = Path(temp)
            (workspace / "target_study").mkdir()
            hidden = workspace / "target_study/paper.pdf"
            hidden.write_bytes(b"hidden")
            (workspace / "alias.pdf").symlink_to(hidden)
            (Path(outside) / "paper.pdf").write_bytes(b"outside")
            (workspace / "escape.pdf").symlink_to(Path(outside) / "paper.pdf")
            args = mineru.build_parser().parse_args(["placeholder", "--workspace", str(workspace)])
            args.excluded_paths = []
            with patch.object(mineru, "source_fingerprint") as fingerprint, \
                    patch.object(mineru, "request_json") as request:
                for source in ("target_study/paper.pdf", "alias.pdf", "escape.pdf", "checklist.pdf",
                               "https://example.test/%74arget_study/paper.pdf"):
                    with self.assertRaises(mineru.MinerUError):
                        mineru.convert_one(source, args)
                fingerprint.assert_not_called()
                request.assert_not_called()
            self.assertEqual(args.output_dir, "artifacts/literature/pdf_markdown")


def load_tests(loader, tests, pattern):
    for name in ("test_retrieve_literature", "test_annotate_retrieval_trace"):
        module = load_module(f"rcbench_bundled_{name}", SCRIPTS / f"{name}.py")
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


if __name__ == "__main__":
    unittest.main()
