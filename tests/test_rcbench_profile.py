from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "benchmarks/researchclawbench/skills/rcbench-workflow-controller/scripts/rcbench.py"
M = runpy.run_path(str(SCRIPT))
G = M["main"].__globals__


def fixture(*, paper=True, complete=False):
    ids = ["I1", "P1"] if paper else ["I1"]
    initial = {"scientific_goals": [{"id": "G1", "objective": "Estimate the treatment effect"}],
               "requirements": [{"id": "I1", "statement": "Compare the two conditions", "goal_ids": ["G1"]}]}
    grounding = {"paper_identity_gate": {"applicable": paper, "pass": paper},
                 "protocol_fingerprint": {"result_contract": [{"id": "P1", "priority": "core"}] if paper else []}}
    refined = {"rubric_items": [{"id": "R1", "source_evidence_ids": ["P1"] if paper else [],
                "requirement_ids": ["I1"], "priority": "core", "required_artifacts": [{"path": "report/figures/effect.svg"}]}],
               "core_completion_gate": [{"source_evidence_id": key, "status": "pass" if complete else "planned", "blocking_gap": ""} for key in ids]}
    final = {
        "overall_pass": complete, "scientific_validity_pass": complete, "task_completion_pass": complete,
        "protocol_coverage_pass": paper and complete,
        "paper_identity_check": {"applicable": paper, "pass": paper},
        "execution_check": {"pass": complete, "missing": [] if complete else ["Treatment runs pending"], "unsupported_claims": []},
        "alignment_check": {"pass": complete, "instruction_omissions": [], "protocol_omissions": [],
                            "wrong_or_weak_substitutions": [], "artifact_mismatches": []},
        "protocol_lock_check": {"pass": complete, "unresolved_fidelity_gaps": []},
        "core_completion_check": [{"source_evidence_id": key, "pass": complete} for key in ids],
        "artifact_checks": [{"path": "report/figures/effect.svg", "present": complete, "data_backed": complete,
                             "form_match": "strong" if complete else "no", "panel_axis_series_match": "strong" if complete else "no", "missing_elements": [] if complete else ["Treatment series"]}],
        "required_fixes": [] if complete else [{"priority": 1, "action": "Run both treatment conditions"}],
    }
    return {"initial_rubric": initial, "grounding_research": grounding, "refined_rubric": refined, "report_rubric_check": final}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rcbench fixture ")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        M["init_workspace"](self.workspace)
        (self.workspace / "INSTRUCTIONS.md").write_text("Compare the two treatment conditions and estimate their effect.")

    def write(self, artifacts, *, figure=False):
        outputs = self.workspace / "outputs"
        outputs.mkdir(exist_ok=True)
        for name, value in artifacts.items():
            (outputs / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
        (self.workspace / "report").mkdir(exist_ok=True)
        (self.workspace / "report/report.md").write_text("# Result\nMeasured effect and its uncertainty.\n", encoding="utf-8")
        if figure:
            path = self.workspace / "report/figures/effect.svg"
            path.parent.mkdir(exist_ok=True)
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")

    def check(self, phase="final"):
        return M["check_workspace"](self.workspace, phase)

    def assert_invalid(self, artifacts, match, *, figure=False, phase="final"):
        self.write(artifacts, figure=figure)
        with self.assertRaisesRegex(M["ContractError"], match):
            self.check(phase)

    def test_planning_is_not_execution(self):
        artifacts = fixture()
        self.write(artifacts)
        self.assertFalse(self.check("plan")["completion"])
        artifacts["refined_rubric"]["core_completion_gate"][0]["status"] = "pass"
        self.assert_invalid(artifacts, "Planning cannot claim", phase="plan")

    def test_missing_and_dangling_core_mappings(self):
        artifacts = fixture()
        artifacts["refined_rubric"]["rubric_items"][0]["source_evidence_ids"] = []
        self.assert_invalid(artifacts, "Unmapped core source", phase="plan")
        artifacts = fixture()
        artifacts["refined_rubric"]["rubric_items"][0]["requirement_ids"] = ["I404"]
        self.assert_invalid(artifacts, "dangling requirement", phase="plan")
        artifacts = fixture()
        artifacts["refined_rubric"]["rubric_items"][0]["priority"] = "supporting"
        self.assert_invalid(artifacts, "Unmapped core instruction", phase="plan")
        artifacts = fixture()
        artifacts["grounding_research"]["protocol_fingerprint"]["result_contract"][0]["requirement_ids"] = ["I404"]
        self.assert_invalid(artifacts, "Source evidence P1 has dangling requirement", phase="plan")

    def test_missing_instruction_core_row_rejected(self):
        artifacts = fixture(complete=True)
        artifacts["report_rubric_check"]["core_completion_check"] = [{"source_evidence_id": "P1", "pass": True}]
        self.assert_invalid(artifacts, "Final core IDs", figure=True)

    def test_instruction_led_success_without_paper(self):
        self.write(fixture(paper=False, complete=True), figure=True)
        result = self.check()
        self.assertTrue(result["completion"])
        self.assertFalse(result["protocol_coverage"])
        self.assertFalse(result["scientific_validation_performed"])

    def test_honest_partial_valid(self):
        artifacts = fixture()
        artifacts["refined_rubric"]["core_completion_gate"] = [
            {"source_evidence_id": key, "status": "blocked", "blocking_gap": "Missing experiment input"} for key in ["I1", "P1"]]
        self.write(artifacts)
        result = self.check()
        self.assertTrue(result["structurally_valid"])
        self.assertFalse(result["completion"])
        self.assertEqual(result["missing_artifacts"], ["report/figures/effect.svg"])

    def test_false_overall_pass_rejected(self):
        artifacts = fixture(complete=True)
        artifacts["report_rubric_check"]["task_completion_pass"] = False
        self.assert_invalid(artifacts, "overall_pass requires", figure=True)

    def test_fidelity_gap_cannot_pass(self):
        artifacts = fixture(complete=True)
        artifacts["report_rubric_check"]["protocol_lock_check"]["unresolved_fidelity_gaps"] = ["Wrong test split"]
        self.assert_invalid(artifacts, "unresolved fidelity", figure=True)

    def test_identity_cannot_waive_locked_protocol(self):
        artifacts = fixture(complete=True)
        artifacts["report_rubric_check"]["paper_identity_check"]["applicable"] = False
        self.assert_invalid(artifacts, "silently change paper applicability", figure=True)

    def test_semantic_mismatch_cannot_pass_core(self):
        artifacts = fixture(complete=True)
        artifacts["report_rubric_check"]["artifact_checks"][0]["form_match"] = "partial"
        self.assert_invalid(artifacts, "Passing core row", figure=True)

    def test_missing_figure_detected_from_filesystem(self):
        self.assert_invalid(fixture(complete=True), "present flag disagrees")

    def test_missing_artifact_check_rejected(self):
        artifacts = fixture(complete=True)
        artifacts["report_rubric_check"]["artifact_checks"] = []
        self.assert_invalid(artifacts, "Missing artifact check", figure=True)

    def test_core_criterion_requires_physical_evidence(self):
        artifacts = fixture(complete=True)
        artifacts["refined_rubric"]["rubric_items"][0]["required_artifacts"] = []
        self.assert_invalid(artifacts, "needs at least one required_artifact", figure=True)

    def test_required_repairs_prevent_overall_pass(self):
        artifacts = fixture(complete=True)
        artifacts["report_rubric_check"]["required_fixes"] = [{"action": "Correct an unsupported conclusion"}]
        self.assert_invalid(artifacts, "unresolved required_fixes", figure=True)

    def test_original_instruction_required(self):
        self.write(fixture())
        (self.workspace / "INSTRUCTIONS.md").write_text("  \n")
        with self.assertRaisesRegex(M["ContractError"], "nonempty INSTRUCTIONS"):
            self.check("plan")

    def test_final_requires_report(self):
        self.write(fixture())
        (self.workspace / "report/report.md").unlink()
        with self.assertRaisesRegex(M["ContractError"], "report/report.md"):
            self.check()

    def test_duplicate_ids_and_keys_rejected(self):
        artifacts = fixture()
        artifacts["refined_rubric"]["core_completion_gate"].append(copy.deepcopy(artifacts["refined_rubric"]["core_completion_gate"][0]))
        self.assert_invalid(artifacts, "Duplicate core gate", phase="plan")
        (self.workspace / "outputs/initial_rubric.json").write_text('{"scientific_goals": [], "scientific_goals": []}')
        with self.assertRaisesRegex(M["ContractError"], "Duplicate object key"):
            self.check("plan")

    def test_workspace_and_hidden_paths_rejected(self):
        for path in ("../escape.csv", "/tmp/outside.csv", "target_study/paper.md", "evaluation/checklist.json", "zh-checklists/data.json", "C:\\hidden.csv"):
            with self.subTest(path=path):
                artifacts = fixture()
                artifacts["refined_rubric"]["rubric_items"][0]["required_artifacts"] = [{"path": path}]
                self.assert_invalid(artifacts, "path|Path", phase="plan")

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.workspace / "escape").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Host does not permit symlinks")
            artifacts = fixture()
            artifacts["refined_rubric"]["rubric_items"][0]["required_artifacts"] = [{"path": "escape/file.csv"}]
            self.assert_invalid(artifacts, "external workspace path", phase="plan")

    def test_supplied_inputs_cannot_be_generated_artifacts(self):
        for path in ("data/observations.csv", "related_work/paper.md"):
            with self.subTest(path=path):
                artifacts = fixture()
                artifacts["refined_rubric"]["rubric_items"][0]["required_artifacts"] = [{"path": path}]
                self.assert_invalid(artifacts, "outside supplied", phase="plan")
                artifacts = fixture()
                check = copy.deepcopy(artifacts["report_rubric_check"]["artifact_checks"][0])
                check["path"] = path
                artifacts["report_rubric_check"]["artifact_checks"].append(check)
                self.assert_invalid(artifacts, "outside supplied")

    def test_supplied_inputs_symlink_alias_cannot_be_generated_artifacts(self):
        supplied = self.workspace / "data"
        supplied.mkdir()
        (supplied / "observations.csv").write_text("condition,value\nA,1\n")
        try:
            (self.workspace / "input_alias").symlink_to(supplied, target_is_directory=True)
        except OSError:
            self.skipTest("Host does not permit symlinks")
        path = "input_alias/observations.csv"
        artifacts = fixture()
        artifacts["refined_rubric"]["rubric_items"][0]["required_artifacts"] = [{"path": path}]
        self.assert_invalid(artifacts, "outside supplied", phase="plan")
        artifacts = fixture()
        check = copy.deepcopy(artifacts["report_rubric_check"]["artifact_checks"][0])
        check.update(path=path, present=True)
        artifacts["report_rubric_check"]["artifact_checks"].append(check)
        self.assert_invalid(artifacts, "outside supplied")

    def test_nonpaper_source_contract_survives_instruction_led_mode(self):
        artifacts = fixture(paper=False)
        artifacts["grounding_research"]["protocol_fingerprint"]["result_contract"] = [{"id": "P1", "priority": "core", "source_type": "instruction"}]
        self.assert_invalid(artifacts, "Unmapped core source", phase="plan")

    def test_cli_partial_exit_zero_but_invalid_claim_exit_two(self):
        artifacts = fixture()
        self.write(artifacts)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(M["main"](["check", "--workspace", str(self.workspace), "--phase", "final"]), 0)
            artifacts["report_rubric_check"]["overall_pass"] = True
            self.write(artifacts)
            self.assertEqual(M["main"](["check", "--workspace", str(self.workspace), "--phase", "final"]), 2)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        M["init_workspace"](self.workspace)
        self.path = self.workspace / ".rcbench/profile.yaml"

    def test_defaults_validate(self):
        profile = M["load_profile"](self.workspace)
        self.assertEqual(profile["workflow"]["max_initial_queries"], 3)
        self.assertEqual(profile["workflow"]["max_followup_queries"], 1)
        self.assertEqual(profile["environments"]["base"]["python"], "python")

    def test_budget_unknown_and_duplicate_fields_rejected(self):
        original = self.path.read_text()
        for value in (-1, None, True, "3"):
            profile = yaml.safe_load(original)
            profile["workflow"]["max_initial_queries"] = value
            self.path.write_text(yaml.safe_dump(profile))
            with self.subTest(value=value), self.assertRaises(M["ContractError"]):
                M["load_profile"](self.workspace)
        self.path.write_text(original + "unknown_key: 1\n")
        with self.assertRaisesRegex(M["ContractError"], "Additional properties"):
            M["load_profile"](self.workspace)
        self.path.write_text(original + "default_environment: ml\n")
        with self.assertRaisesRegex(M["ContractError"], "Duplicate"):
            M["load_profile"](self.workspace)

    def test_init_preserves_user_profile_and_does_not_start_run(self):
        self.path.write_text(self.path.read_text() + "# User configuration\n")
        before = self.path.read_bytes()
        self.assertEqual(M["init_workspace"](self.workspace)["created"], [])
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse((self.workspace / "outputs/rcbench_run_manifest.json").exists())

    def test_start_records_hashes_without_credentials_and_never_overwrites(self):
        with patch.dict("os.environ", {"TAVILY_API_KEY": "SECRET_VALUE"}):
            result = M["start_workspace"](self.workspace)
        self.assertEqual(result["created"], ["outputs/rcbench_run_manifest.json"])
        path = self.workspace / "outputs/rcbench_run_manifest.json"
        before = path.read_text()
        manifest = json.loads(before)
        self.assertNotIn("SECRET_VALUE", before)
        self.assertEqual({key.split('/')[0] for key in manifest["skill_files_sha256"]}, set(M["SKILL_NAMES"]))
        self.assertEqual(M["start_workspace"](self.workspace)["created"], [])
        profile = M["load_profile"](self.workspace)
        profile["workflow"]["max_figures"] = 8
        self.path.write_text(yaml.safe_dump(profile))
        with self.assertRaisesRegex(M["ContractError"], "manifest differs"):
            M["start_workspace"](self.workspace)
        self.assertEqual(path.read_text(), before)

    def test_doctor_optional_env_absence_is_informational(self):
        profile = M["load_profile"](self.workspace)
        profile["environments"]["base"]["python"] = sys.executable
        self.path.write_text(yaml.safe_dump(profile))
        files_before = {path.relative_to(self.workspace) for path in self.workspace.rglob("*")}
        with patch("subprocess.run", side_effect=AssertionError("doctor must not execute environments")):
            result = M["doctor"](self.workspace, profile)
        self.assertTrue(result["ok"])
        self.assertFalse(result["environments"]["ml"]["available"])
        self.assertFalse(result["imports_checked"])
        self.assertEqual(files_before, {path.relative_to(self.workspace) for path in self.workspace.rglob("*")})

    def test_dependency_error_is_actionable(self):
        with patch.dict(sys.modules, {"yaml": None}):
            with self.assertRaisesRegex(M["ContractError"], "pip install"):
                M["dependencies"]()

    def test_credentials_and_unsafe_retrieval_paths_rejected(self):
        profile = M["load_profile"](self.workspace)
        profile["retrieval"]["providers"]["tavily"]["api_key"] = "secret"
        self.path.write_text(yaml.safe_dump(profile))
        with self.assertRaises(M["ContractError"]):
            M["load_profile"](self.workspace)
        del profile["retrieval"]["providers"]["tavily"]["api_key"]
        profile["retrieval"]["providers"]["local_literature"]["paths"] = ["target_study"]
        self.path.write_text(yaml.safe_dump(profile))
        with self.assertRaisesRegex(M["ContractError"], "Forbidden"):
            M["load_profile"](self.workspace)


if __name__ == "__main__":
    unittest.main()
