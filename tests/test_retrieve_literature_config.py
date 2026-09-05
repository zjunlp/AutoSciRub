from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/autoscirub/skills/scientific-literature-grounding/scripts/retrieve_literature.py"
M = runpy.run_path(str(SCRIPT))
G = M["main"].__globals__


@contextlib.contextmanager
def aliased_project_directory():
    """Exercise path aliases on Linux too, not only macOS/Windows temp paths."""
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        project.mkdir()
        alias = Path(temp) / "project-alias"
        try:
            alias.symlink_to(project, target_is_directory=True)
        except OSError:
            # Windows may prohibit symlinks; its temp path can still be an 8.3 alias.
            yield str(project)
        else:
            yield str(alias)


class ConfigTests(unittest.TestCase):
    def test_comments_quotes_inline_lists_and_anchors(self):
        parsed = M["read_yaml"]('state_dir: &state "results#one"\nretrieval:\n'
                                '  enabled_sources: [arxiv] # note\n'
                                '  exclusions:\n    blocked_titles:\n      - "one # two"\n'
                                '      - *state\n')
        M["validate_config"](parsed)
        self.assertEqual(parsed["retrieval"]["enabled_sources"], ["arxiv"])
        self.assertEqual(parsed["retrieval"]["exclusions"]["blocked_titles"], ["one # two", "results#one"])

    def test_official_example(self):
        cfg = M["try_load_yaml"](ROOT / "config/sources.example.yaml")
        M["validate_config"](cfg)
        self.assertIn("arxiv", cfg["retrieval"]["enabled_sources"])

    def test_invalid_yaml_roots_and_duplicates(self):
        for text in ("", "false", "[]", "null", "- arxiv", "state_dir: a\nstate_dir: b", "retrieval: ["):
            with self.subTest(text=text), self.assertRaises(M["ConfigError"]):
                M["read_yaml"](text)

    def test_unknown_fields_types_and_names(self):
        for data in (
            {"retrieval": {"enabled_soruces": []}},
            {"retrieval": {"enabled_sources": ["arxvi"]}},
            {"retrieval": {"enabled_sources": ["arxiv", "arxiv"]}},
            {"retrieval": {"enabled_sources": {}}},
            {"retrieval": {"providers": {"arxiv": {"enabled": "false"}}}},
            {"retrieval": {"limits": {"max_results_per_query": True}}},
            {"retrieval": {"limits": {"max_queries_per_goal": 0}}},
            {"retrieval": {"exclusions": {"excluded_paths": [" "]}}},
            {"state_dir": ""},
            {"retrieval": None},
        ):
            with self.subTest(data=data), self.assertRaises(M["ConfigError"]):
                M["validate_config"](data)

    def test_partial_overrides_and_zero_optional_limits(self):
        M["validate_config"]({"retrieval": {"limits": {"max_supplemental_sources": 0}}})
        M["validate_config"]({})
        M["validate_config"](M["DEFAULT_CONFIG"])

    def test_integral_float_limits_work_after_schema_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.yaml"
            config.write_text("retrieval:\n  limits:\n    max_queries_per_goal: 5.0\n")
            cfg = M["load_config"](config)
            count = cfg["retrieval"]["limits"]["max_queries_per_goal"]
            self.assertIs(type(count), int)
            self.assertEqual(M["build_queries"]([{"title": "test"}], count), [("G1", "test")])

    def test_missing_dependency_is_actionable(self):
        for dependency in ("yaml", "jsonschema"):
            with patch.dict(sys.modules, {dependency: None}), self.assertRaisesRegex(M["ConfigError"], "pip install"):
                M["dependencies"]()

    def test_config_discovery_and_state_precedence(self):
        with aliased_project_directory() as temp:
            project = Path(temp)
            (project / ".autoscirub").mkdir()
            (project / ".autoscirub/config.yaml").write_text("state_dir: from-config\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(M["load_config"](project=project)["state_dir"], str((project / "from-config").resolve()))
                with patch.dict(os.environ, {"AUTOSCIRUB_STATE_DIR": "from-env"}):
                    self.assertEqual(M["load_config"](project=project)["state_dir"], str((project / "from-env").resolve()))
                    self.assertEqual(M["load_config"](project=project, state_dir="from-cli")["state_dir"],
                                     str((project / "from-cli").resolve()))
            with self.assertRaisesRegex(M["ConfigError"], "not found"):
                M["load_config"](project / "absent.yaml", project=project)

    def test_schema_is_packaged_and_editor_reference_resolves_locally(self):
        wrapper = json.loads((ROOT / "config/sources.schema.json").read_text())
        path = (ROOT / "config" / wrapper["$ref"]).resolve()
        self.assertTrue(path.is_file())
        from jsonschema import Draft202012Validator
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        self.assertTrue(Draft202012Validator(schema).is_valid(M["DEFAULT_CONFIG"]))


class LocalRetrievalTests(unittest.TestCase):
    def test_exclusions_same_filename_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            for directory in ("papers/allowed", "papers/other", "papers/excluded", "papers/excluded-lookalike"):
                folder = project / directory
                folder.mkdir(parents=True)
                (folder / "paper.md").write_text("fixture", encoding="utf-8")
            try:
                (project / "papers/allowed/link.md").symlink_to(project / "papers/excluded/paper.md")
            except OSError:
                pass  # Windows runners may not permit symlink creation.
            result = M["collect_local_literature"](["papers"], ["papers/excluded"], project)
            self.assertEqual(len(result), 3)
            self.assertEqual(len(M["dedupe_sources"](result)), 3)
            self.assertFalse(any("/excluded/" in item["url"].replace("\\", "/") for item in result))

    def test_explicit_missing_path_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                M["collect_local_literature"](["missing"], [], Path(temp))

    def test_domain_exclusion_matches_domain_boundary(self):
        self.assertTrue(M["is_blocked"]("paper", [], ["example.org"], "https://sub.example.org/paper"))
        self.assertFalse(M["is_blocked"]("paper", [], ["example.org"], "https://notexample.org/paper"))


class RetrievalBehaviorTests(unittest.TestCase):
    def run_main(self, project, *extra):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return M["main"](["--project", str(project), *extra])

    def test_repeated_queries_preserved_and_local_scan_once(self):
        config = M["deep_merge"](M["DEFAULT_CONFIG"], {
            "retrieval": {"enabled_sources": ["local_literature"], "local_literature": {"paths": ["papers"]}}})
        pairs = M["build_queries"]([{"goal_id": "G0", "queries": ["first", "second"]}], 5)
        self.assertEqual(pairs, [("G0", "first"), ("G0", "second")])
        with patch.dict(G, {"collect_local_literature": unittest.mock.Mock(return_value=[])}):
            with contextlib.redirect_stderr(io.StringIO()):
                M["retrieve"](config, pairs, Path.cwd())
            G["collect_local_literature"].assert_called_once()

    def test_statuses_missing_key_empty_and_partial(self):
        cfg = M["deep_merge"](M["DEFAULT_CONFIG"], {
            "retrieval": {"enabled_sources": ["arxiv", "openalex", "tavily"],
                          "providers": {"tavily": {"enabled": True}}}})
        with patch.dict(os.environ, {}, clear=True), patch.dict(G, {
            "search_arxiv": unittest.mock.Mock(return_value=[]),
            "search_openalex": unittest.mock.Mock(side_effect=TimeoutError),
        }), contextlib.redirect_stderr(io.StringIO()):
            sources, trace = M["retrieve"](cfg, [("G0", "test")], Path.cwd())
        self.assertEqual(sources, [])
        self.assertEqual([e["status"] for e in trace], ["empty", "failed", "skipped"])
        self.assertEqual(M["retrieval_status"](trace), "partial")
        self.assertIn("TAVILY_API_KEY", trace[-1]["reason"])

    def test_failure_preserves_old_index_and_redacts_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            state = project / ".autoscirub"
            state.mkdir()
            (state / "config.yaml").write_text("retrieval:\n  enabled_sources: [arxiv]\n")
            out = state / "literature_sources.json"
            out.write_text('{"previous": true}')
            exc = urllib.error.HTTPError("https://api.example/?api_key=SECRET", 401, "SECRET", {}, None)
            with patch.dict(os.environ, {}, clear=True), patch.dict(G, {
                "search_arxiv": unittest.mock.Mock(side_effect=exc)
            }):
                status = self.run_main(project, "--query", "test")
            self.assertEqual(status, 3)
            self.assertEqual(json.loads(out.read_text()), {"previous": True})
            diagnostic = (state / "literature_sources.failure.json").read_text()
            self.assertNotIn("SECRET", diagnostic)
            self.assertIn("HTTP 401", diagnostic)

    def test_empty_success_and_invalid_goals(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".autoscirub").mkdir()
            (project / ".autoscirub/config.yaml").write_text("retrieval:\n  enabled_sources: [arxiv]\n")
            with patch.dict(os.environ, {}, clear=True), patch.dict(G, {
                "search_arxiv": unittest.mock.Mock(return_value=[])
            }):
                self.assertEqual(self.run_main(project, "--query", "test"), 0)
                self.assertEqual(self.run_main(project, "--query", " "), 2)
                self.assertEqual(self.run_main(project, "--goals", "missing.json"), 2)
            result = json.loads((project / ".autoscirub/literature_sources.json").read_text())
            self.assertEqual(result["status"], "empty")

    def test_no_enabled_sources_is_unavailable(self):
        self.assertEqual(M["retrieval_status"]([]), "unavailable")

    def test_openalex_doi_url(self):
        with patch.dict(G, {"http_get_json": lambda *a, **kw: {
                "results": [{"title": "Paper", "doi": "https://doi.org/10.1/test"}]}}):
            self.assertEqual(M["search_openalex"]("query", 1, None)[0]["url"], "https://doi.org/10.1/test")


class CLIIntegrationTests(unittest.TestCase):
    def call(self, script, *args, cwd=None):
        env = dict(os.environ)
        env.pop("AUTOSCIRUB_STATE_DIR", None)
        return subprocess.run([sys.executable, "-B", str(ROOT / script), *map(str, args)],
                              cwd=cwd or ROOT, env=env, capture_output=True, text=True)

    def test_demo_from_outside_repository_and_doctor(self):
        with tempfile.TemporaryDirectory(prefix="autoscirub test ") as temp:
            project = Path(temp) / "research project"
            demo = self.call("scripts/autoscirub.py", "demo", "--project", project, cwd=temp)
            self.assertEqual(demo.returncode, 0, demo.stderr)
            doctor = self.call("scripts/autoscirub.py", "doctor", "--project", project)
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            repeated = self.call("scripts/autoscirub.py", "demo", "--project", project)
            self.assertNotEqual(repeated.returncode, 0)

    def test_init_preserves_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.call("scripts/autoscirub.py", "init", "--project", temp).returncode, 0)
            path = Path(temp) / ".autoscirub/config.yaml"
            path.write_text("state_dir: custom\n")
            self.assertEqual(self.call("scripts/autoscirub.py", "init", "--project", temp).returncode, 0)
            self.assertEqual(path.read_text(), "state_dir: custom\n")

    def test_direct_script_missing_dependencies_no_traceback(self):
        result = subprocess.run([sys.executable, "-S", "-B", str(SCRIPT), "--validate-config"],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("pip install", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_demo_missing_dependencies_leaves_destination_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "demo"
            result = subprocess.run([sys.executable, "-S", "-B", str(ROOT / "scripts/autoscirub.py"),
                                     "demo", "--project", str(destination)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(destination.exists())

    def test_mineru_state_path_without_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.call("plugins/autoscirub/skills/mineru-pdf-to-markdown/scripts/mineru_pdf_to_markdown.py",
                               "--project", temp, "--state-dir", "custom", "absent.pdf")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse((Path(temp) / "related_work").exists())

    def test_mineru_resolves_config_env_and_explicit_destination(self):
        mineru = runpy.run_path(str(ROOT / "plugins/autoscirub/skills/mineru-pdf-to-markdown/scripts/mineru_pdf_to_markdown.py"))
        with aliased_project_directory() as temp:
            project = Path(temp)
            (project / "paper.pdf").write_bytes(b"test fixture, no upload")
            (project / ".autoscirub").mkdir()
            (project / ".autoscirub/config.yaml").write_text("state_dir: config-state\n")
            for extra, env, expected in (
                ([], {}, project / "config-state/cache/mineru"),
                ([], {"AUTOSCIRUB_STATE_DIR": "env-state"}, project / "env-state/cache/mineru"),
                (["--output-dir", "explicit"], {"AUTOSCIRUB_STATE_DIR": "env-state"}, project / "explicit"),
            ):
                called = []
                def convert(source, args):
                    called.append(args.output_dir)
                    return {"status": "completed"}
                with patch.dict(os.environ, env, clear=True), patch.dict(mineru["main"].__globals__, {"convert_one": convert}), \
                     patch.object(sys, "argv", ["mineru", "--project", temp, *extra, "paper.pdf"]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(mineru["main"](), 0)
                self.assertEqual(called, [str(expected.resolve())])


if __name__ == "__main__":
    unittest.main()
