from __future__ import annotations
import contextlib
import io
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import shutil

ROOT = Path(__file__).resolve().parents[1]
M = runpy.run_path(str(ROOT / "scripts/install.py"))


class InstallTests(unittest.TestCase):
    def test_complete_install_repeat_and_check(self):
        with tempfile.TemporaryDirectory(prefix="install with spaces ") as temp, contextlib.redirect_stdout(io.StringIO()):
            target = Path(temp) / "skills"
            M["install"](target)
            self.assertEqual({p.name for p in target.iterdir()}, M["EXPECTED_SKILLS"])
            M["install"](target)
            M["install"](target, check=True)
            self.assertTrue((target / "scientific-literature-grounding/references/config.schema.json").is_file())
            self.assertTrue((target / "scientific-literature-grounding/requirements.txt").is_file())

    def test_conflict_is_detected_before_any_install(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            conflict = target / "targeted-revision"
            conflict.mkdir()
            original = conflict / "SKILL.md"
            original.write_text("My own skill")
            with self.assertRaisesRegex(ValueError, "unmanaged"):
                M["install"](target)
            self.assertEqual(list(target.iterdir()), [conflict])
            self.assertEqual(original.read_text(), "My own skill")

    def test_local_modification_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            target = Path(temp)
            M["install"](target)
            file = target / "autoscirub/SKILL.md"
            file.write_text("My edits")
            with self.assertRaisesRegex(ValueError, "Locally edited"):
                M["install"](target)
            self.assertEqual(file.read_text(), "My edits")
            with self.assertRaisesRegex(ValueError, "out-of-date"):
                M["install"](target, check=True)

    def test_dry_run_does_not_create_target(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            target = Path(temp) / "not-created"
            M["install"](target, dry_run=True)
            self.assertFalse(target.exists())

    def test_all_platforms_resolve_distinct_directories(self):
        targets = [M["destination"](p) for p in ("codex", "claude", "openclaw")]
        self.assertEqual(len(set(targets)), 3)
        self.assertTrue(all(p.name == "skills" for p in targets))

    def test_installed_retriever_is_self_contained(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            target = Path(temp) / "skills"
            M["install"](target)
            script = target / "scientific-literature-grounding/scripts/retrieve_literature.py"
            result = subprocess.run([sys.executable, "-B", str(script), "--validate-config"],
                                    cwd=temp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_unmodified_owned_install_can_update(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            source = Path(temp) / "source"
            shutil.copytree(M["SOURCE"], source)
            target = Path(temp) / "installed"
            with patch.dict(M["install"].__globals__, {"SOURCE": source}):
                M["install"](target)
                skill = source / "autoscirub/SKILL.md"
                original = skill.read_text(encoding="utf-8")
                skill.write_text(original + "\nUpdated fixture.\n", encoding="utf-8")
                M["install"](target)
                self.assertEqual((target / "autoscirub/SKILL.md").read_text(encoding="utf-8"), skill.read_text(encoding="utf-8"))
                M["install"](target, check=True)

    def test_benchmark_bundle_coexists_without_replacing_generic_skills(self):
        with tempfile.TemporaryDirectory(prefix="adapter with spaces ") as temp, contextlib.redirect_stdout(io.StringIO()):
            target = Path(temp) / "skills"
            M["install"](target)
            before = M["inventory"](target / "mineru-pdf-to-markdown")
            M["install"](target, bundle="researchclawbench")
            self.assertEqual({p.name for p in target.iterdir()}, M["EXPECTED_SKILLS"] | M["RCBENCH_SKILLS"])
            self.assertEqual(before, M["inventory"](target / "mineru-pdf-to-markdown"))
            M["install"](target, bundle="researchclawbench", check=True)
            helper = target / "rcbench-workflow-controller/scripts/rcbench.py"
            initialized = subprocess.run([sys.executable, "-B", str(helper), "init", "--workspace", temp],
                                         cwd=temp, capture_output=True, text=True)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            result = subprocess.run([sys.executable, "-B", str(helper), "config", "--workspace", temp],
                                    cwd=temp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_benchmark_conflict_preflights_the_entire_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            conflict = target / "rcbench-workflow-controller"
            conflict.mkdir()
            (conflict / "SKILL.md").write_text("Local method")
            with self.assertRaisesRegex(ValueError, "unmanaged"):
                M["install"](target, bundle="researchclawbench")
            self.assertEqual(list(target.iterdir()), [conflict])

    def test_cli_rejects_installation_into_either_source_tree(self):
        for bundle in ("generic", "researchclawbench"):
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/install.py"), "codex",
                                     "--bundle", bundle, "--skills-dir", str(M["RCBENCH_SOURCE"]), "--dry-run"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("outside the source", result.stderr)


if __name__ == "__main__":
    unittest.main()
