#!/usr/bin/env python3
"""Configure an RCBench workspace and check evidence-contract consistency.

This tool never runs research or judges scientific correctness. A valid partial
report exits 0; malformed or contradictory completion claims exit 2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "references"
ADAPTATION_VERSION = "0.1.0"
SOURCE_SKILL_VERSION = "skills-0901-r2"
PROFILE_PATH = ".rcbench/profile.yaml"
MANIFEST_PATH = "outputs/rcbench_run_manifest.json"
SKILL_NAMES = (
    "rcbench-workflow-controller", "rcbench-instruction-rubric",
    "rcbench-grounding-research", "rcbench-experiments-design",
    "rcbench-report-verifier", "rcbench-mineru-pdf-to-markdown",
)


class ContractError(ValueError):
    pass


def dependencies():
    try:
        import yaml
        import jsonschema
    except ImportError as exc:
        raise ContractError("Install helper dependencies: python -m pip install PyYAML jsonschema") from exc
    return yaml, jsonschema


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"Duplicate object key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, ValueError) as exc:
        raise ContractError(f"Cannot read JSON {path.name}: {exc}") from exc


def blocked_path(path: Path) -> bool:
    return any(re.search(r"(?:^|[-_.])(?:target[-_]?study|checklists?)(?:$|[-_.])", part, re.I)
               for part in path.parts)


def workspace_path(workspace: Path, value: str) -> Path:
    """Reject traversal, hidden evaluation material, and outward symlinks."""
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise ContractError(f"Expected a workspace-relative POSIX path: {value!r}")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or re.match(r"^[A-Za-z]:", value):
        raise ContractError(f"Path must stay inside the workspace: {value}")
    resolved = (workspace / relative).resolve()
    if not resolved.is_relative_to(workspace) or blocked_path(relative) or blocked_path(resolved.relative_to(workspace)):
        raise ContractError(f"Forbidden or external workspace path: {value}")
    return resolved


def generated_artifact_path(workspace: Path, value: str) -> Path:
    resolved = workspace_path(workspace, value)
    supplied_roots = [(workspace / name).resolve() for name in ("data", "related_work")]
    if any(resolved.is_relative_to(root) for root in supplied_roots):
        raise ContractError(f"Required evidence must be generated outside supplied data/ and related_work/: {value}")
    return resolved


def validate_schema(value, schema, label):
    _, jsonschema = dependencies()
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.path)) or "<root>"
        raise ContractError(f"{label}.{location}: {error.message}")


def load_profile(workspace: Path, *, default=False):
    yaml, _ = dependencies()

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        return unique_pairs((loader.construct_object(k, deep=deep), loader.construct_object(v, deep=deep))
                            for k, v in node.value)

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    path = REFERENCE_DIR / "profile.yaml" if default else workspace_path(workspace, PROFILE_PATH)
    try:
        profile = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"Cannot read profile {path}; run init first or fix YAML: {exc}") from exc
    validate_schema(profile, read_json(REFERENCE_DIR / "profile.schema.json"), "profile")
    if profile["default_environment"] not in profile["environments"]:
        raise ContractError("profile.default_environment must name a configured environment")
    for name, entry in profile["environments"].items():
        executable = entry["python"]
        if any(char in executable for char in "\r\n\0"):
            raise ContractError(f"Invalid Python executable for environment {name}")
        if not Path(executable).is_absolute() and ("/" in executable or "\\" in executable):
            workspace_path(workspace, executable.replace("\\", "/"))
    retrieval = profile["retrieval"]
    for provider in retrieval["providers"].values():
        for value in provider.get("paths", []):
            workspace_path(workspace, value)
        for key in ("api_key_env", "base_url_env", "email_env"):
            if key in provider and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", provider[key]):
                raise ContractError(f"{key} must contain an environment variable name, never a credential")
    # Exclusions can name prohibited locations, but never escape the workspace.
    for value in retrieval["exclusions"]["excluded_paths"]:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ContractError(f"Excluded path must be workspace-relative: {value}")
    return profile


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def skill_hashes():
    root = Path(__file__).resolve().parents[2]
    hashes = {}
    for name in SKILL_NAMES:
        folder = root / name
        if not folder.is_dir():
            raise ContractError(f"Incomplete adaptation installation: missing sibling skill {name}")
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not path.is_symlink() and path.suffix in {".md", ".py", ".yaml", ".json"}:
                if not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(root).parts):
                    hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def init_workspace(workspace):
    # Validate configuration before changing the workspace; users can then edit it.
    profile_path = workspace_path(workspace, PROFILE_PATH)
    load_profile(workspace, default=not profile_path.exists())
    created = []
    if not profile_path.exists():
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with profile_path.open("x", encoding="utf-8") as handle:
            handle.write((REFERENCE_DIR / "profile.yaml").read_text(encoding="utf-8"))
        created.append(PROFILE_PATH)
    return {"created": created, "message": "Prepare environments and edit the profile, then run start to snapshot this run. No research was executed."}


def start_workspace(workspace):
    profile = load_profile(workspace)
    hashes = skill_hashes()
    manifest_path = workspace_path(workspace, MANIFEST_PATH)
    created = []
    expected = {"schema_version": "1.0", "adaptation_version": ADAPTATION_VERSION,
                "source_skill_version": SOURCE_SKILL_VERSION, "profile_sha256": digest(profile),
                "skill_files_sha256": hashes}
    if not manifest_path.exists():
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {**expected, "initialized_at": datetime.now(timezone.utc).isoformat()}
        with manifest_path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        created.append(MANIFEST_PATH)
    else:
        manifest = read_json(manifest_path)
    require(isinstance(manifest, dict), "Run manifest must contain a JSON object")
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ContractError("Run manifest differs from the current profile or skills. Use a new run workspace or explicitly archive the previous run; existing provenance was preserved.")
    return {"created": created, "manifest_stale": False,
            "message": "Run provenance recorded; no research or external requests were executed."}


def doctor(workspace, profile):
    environments = {}
    for name, entry in profile["environments"].items():
        value = entry["python"]
        if Path(value).is_absolute():
            candidate = Path(value)
        elif "/" in value or "\\" in value:
            candidate = workspace_path(workspace, value.replace("\\", "/"))
        else:
            found = shutil.which(value)
            candidate = Path(found) if found else None
        environments[name] = {"configured": value, "available": bool(candidate and candidate.is_file() and os.access(candidate, os.X_OK)),
                              "selected": name == profile["default_environment"]}
    return {"ok": environments[profile["default_environment"]]["available"],
            "helper_dependencies": {"PyYAML": True, "jsonschema": True}, "environments": environments,
            "imports_checked": False, "network_checked": False,
            "message": "Only executable availability is checked; prepare and validate scientific dependencies yourself."}


STRING = {"type": "string", "minLength": 1, "pattern": r"\S"}
STRINGS = {"type": "array", "items": STRING, "uniqueItems": True}
BOOL = {"type": "boolean"}
PRIORITY = {"enum": ["core", "supporting"]}


def object_schema(properties, required=None):
    # Scientific artifacts can carry domain-specific evidence alongside this minimum contract.
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required}


def rows(schema, minimum=0):
    return {"type": "array", "items": schema, "minItems": minimum}


INITIAL_SCHEMA = object_schema({
    "scientific_goals": rows(object_schema({"id": STRING, "objective": STRING}), 1),
    "requirements": rows(object_schema({"id": STRING, "statement": STRING, "goal_ids": STRINGS}), 1),
})
GROUNDING_SCHEMA = object_schema({
    "paper_identity_gate": object_schema({"applicable": BOOL, "pass": BOOL}),
    "protocol_fingerprint": object_schema({"result_contract": rows(object_schema({
        "id": STRING, "priority": PRIORITY,
        "source_type": {"enum": ["public_paper", "instruction", "compatible_public_sources"]},
        "requirement_ids": STRINGS,
    }, ["id", "priority"]))}),
})
REFINED_SCHEMA = object_schema({
    "rubric_items": rows(object_schema({"id": STRING, "source_evidence_ids": STRINGS,
        "requirement_ids": STRINGS, "priority": PRIORITY,
        "required_artifacts": rows(object_schema({"path": STRING}))}), 1),
    "core_completion_gate": rows(object_schema({"source_evidence_id": STRING,
        "status": {"enum": ["planned", "in_progress", "partial", "pass", "blocked"]},
        "blocking_gap": {"type": "string"}})),
})
FINAL_SCHEMA = object_schema({
    "overall_pass": BOOL, "scientific_validity_pass": BOOL, "task_completion_pass": BOOL, "protocol_coverage_pass": BOOL,
    "paper_identity_check": object_schema({"applicable": BOOL, "pass": BOOL}),
    "execution_check": object_schema({"pass": BOOL, "missing": STRINGS, "unsupported_claims": STRINGS}),
    "alignment_check": object_schema({"pass": BOOL, "instruction_omissions": STRINGS, "protocol_omissions": STRINGS,
                                      "wrong_or_weak_substitutions": STRINGS, "artifact_mismatches": STRINGS}),
    "protocol_lock_check": object_schema({"pass": BOOL, "unresolved_fidelity_gaps": STRINGS}),
    "core_completion_check": rows(object_schema({"source_evidence_id": STRING, "pass": BOOL})),
    "artifact_checks": rows(object_schema({"path": STRING, "present": BOOL, "data_backed": BOOL,
        "form_match": {"enum": ["strong", "partial", "no"]}, "panel_axis_series_match": {"enum": ["strong", "partial", "no"]},
        "missing_elements": STRINGS})),
    "required_fixes": {"type": "array"},
})


def keyed(values, key, label):
    result = {}
    for row in values:
        value = row[key]
        if value in result:
            raise ContractError(f"Duplicate {label}: {value}")
        result[value] = row
    return result


def require(condition, message):
    if not condition:
        raise ContractError(message)


def check_workspace(workspace, phase):
    instruction = workspace_path(workspace, "INSTRUCTIONS.md")
    require(instruction.is_file() and instruction.read_text(encoding="utf-8").strip(), "Check requires nonempty INSTRUCTIONS.md")
    artifacts = {}
    for name, schema in (("initial_rubric", INITIAL_SCHEMA), ("grounding_research", GROUNDING_SCHEMA), ("refined_rubric", REFINED_SCHEMA)):
        artifacts[name] = read_json(workspace_path(workspace, f"outputs/{name}.json"))
        validate_schema(artifacts[name], schema, name)
    initial, grounding, refined = (artifacts[name] for name in ("initial_rubric", "grounding_research", "refined_rubric"))
    goals = keyed(initial["scientific_goals"], "id", "scientific goal ID")
    requirements = keyed(initial["requirements"], "id", "instruction requirement ID")
    goal_refs = set()
    for row in requirements.values():
        refs = set(row["goal_ids"])
        require(refs and refs <= goals.keys(), f"Requirement {row['id']} has missing or dangling goal_ids")
        goal_refs |= refs
    require(goal_refs == goals.keys(), "Every scientific goal must have an instruction requirement")
    sources = keyed(grounding["protocol_fingerprint"]["result_contract"], "id", "source evidence ID")
    require(not requirements.keys() & sources.keys(), "Instruction requirement and source evidence IDs must be distinct")
    for row in sources.values():
        require(set(row.get("requirement_ids", [])) <= requirements.keys(), f"Source evidence {row['id']} has dangling requirement_ids")
    identity = grounding["paper_identity_gate"]
    require(identity["applicable"] or not identity["pass"], "Inapplicable paper identity cannot claim pass")
    source_core = {key for key, row in sources.items() if row["priority"] == "core" and
                   (identity["applicable"] or row.get("source_type", "public_paper") != "public_paper")}
    expected_core = set(requirements) | source_core
    rubric = keyed(refined["rubric_items"], "id", "rubric item ID")
    mapped_requirements, mapped_sources, expected_artifacts, critical_artifacts = set(), set(), set(), set()
    item_paths = {}
    for row in rubric.values():
        requirement_refs, source_refs = set(row["requirement_ids"]), set(row["source_evidence_ids"])
        require(requirement_refs <= requirements.keys(), f"Rubric {row['id']} has dangling requirement_ids")
        require(source_refs <= sources.keys(), f"Rubric {row['id']} has dangling source_evidence_ids")
        require(requirement_refs or source_refs, f"Rubric {row['id']} has no instruction or source mapping")
        if row["priority"] == "core":
            mapped_requirements |= requirement_refs
            mapped_sources |= source_refs
        paths = [entry["path"] for entry in row["required_artifacts"]]
        require(row["priority"] != "core" or paths, f"Core rubric {row['id']} needs at least one required_artifact (a proof or report file is valid)")
        require(len(paths) == len(set(paths)), f"Rubric {row['id']} repeats an artifact path")
        for path in paths:
            generated_artifact_path(workspace, path)
        item_paths[row["id"]] = set(paths)
        expected_artifacts.update(paths)
        if row["priority"] == "core":
            critical_artifacts.update(paths)
    require(mapped_requirements == requirements.keys(), f"Unmapped core instruction requirements: {sorted(requirements.keys() - mapped_requirements)}")
    require(source_core <= mapped_sources, f"Unmapped core source evidence: {sorted(source_core - mapped_sources)}")
    gates = keyed(refined["core_completion_gate"], "source_evidence_id", "core gate ID")
    require(set(gates) == expected_core, f"Core gate IDs must match applicable obligations; missing={sorted(expected_core - gates.keys())}, extra={sorted(gates.keys() - expected_core)}")
    for key, gate in gates.items():
        require(gate["status"] not in {"partial", "blocked"} or gate["blocking_gap"].strip(), f"Core gate {key} must explain its blocking_gap")
        require(gate["status"] != "pass" or not gate["blocking_gap"].strip(), f"Passing core gate {key} still has a blocking_gap")
    result = {"phase": phase, "structurally_valid": True, "completion": False,
              "scientific_validation_performed": False,
              "message": "Structural consistency only; scientific and figure judgments remain the agent's responsibility.",
              "applicable_core_ids": sorted(expected_core)}
    if phase == "plan":
        require(not any(row["status"] == "pass" for row in gates.values()), "Planning cannot claim execution pass; use planned/in_progress/partial/blocked")
        return result
    report = workspace_path(workspace, "report/report.md")
    require(report.is_file() and report.stat().st_size > 0, "Final check requires nonempty report/report.md")
    final = read_json(workspace_path(workspace, "outputs/report_rubric_check.json"))
    validate_schema(final, FINAL_SCHEMA, "report_rubric_check")
    final_identity = final["paper_identity_check"]
    require(final_identity["applicable"] == identity["applicable"], "Verifier cannot silently change paper applicability; revise the grounding contract first")
    require(not final_identity["pass"] or identity["pass"], "Verifier identity pass conflicts with the grounding identity gate")
    core = keyed(final["core_completion_check"], "source_evidence_id", "core completion ID")
    require(set(core) == expected_core, f"Final core IDs must match applicable obligations; missing={sorted(expected_core - core.keys())}, extra={sorted(core.keys() - expected_core)}")
    for key, row in core.items():
        require(row["pass"] == (gates[key]["status"] == "pass"), f"Core completion {key} disagrees with refined gate status")
    checks = keyed(final["artifact_checks"], "path", "artifact check path")
    require(expected_artifacts <= checks.keys(), f"Missing artifact check rows: {sorted(expected_artifacts - checks.keys())}")
    artifact_ok = {}
    for path, check in checks.items():
        target = generated_artifact_path(workspace, path)
        present = target.is_file() and target.stat().st_size > 0
        require(check["present"] == present, f"Artifact present flag disagrees with filesystem: {path}")
        require(present or not check["data_backed"], f"Missing artifact cannot be data_backed: {path}")
        artifact_ok[path] = present and check["data_backed"] and check["form_match"] == "strong" and check["panel_axis_series_match"] == "strong" and not check["missing_elements"]
    # A core row cannot pass while an artifact required by its mapped criterion fails.
    for key, row in core.items():
        required_paths = set().union(*(item_paths[item["id"]] for item in rubric.values()
                                      if key in item["requirement_ids"] or key in item["source_evidence_ids"]))
        require(not row["pass"] or all(artifact_ok[path] for path in required_paths), f"Passing core row {key} has missing or mismatched required artifacts")
    execution = final["execution_check"]
    alignment = final["alignment_check"]
    protocol = final["protocol_lock_check"]
    require(not execution["pass"] or not (execution["missing"] or execution["unsupported_claims"]), "execution_check.pass conflicts with missing evidence or unsupported claims")
    require(not alignment["pass"] or not any(alignment[name] for name in ("instruction_omissions", "protocol_omissions", "wrong_or_weak_substitutions", "artifact_mismatches")), "alignment_check.pass conflicts with omissions or mismatches")
    require(not protocol["pass"] or not protocol["unresolved_fidelity_gaps"], "protocol_lock_check.pass conflicts with unresolved fidelity gaps")
    all_core_pass = all(row["pass"] for row in core.values())
    critical_ok = all(artifact_ok[path] for path in critical_artifacts)
    paper_ok = not identity["applicable"] or (identity["pass"] and final_identity["pass"] and final["protocol_coverage_pass"])
    require(not final["protocol_coverage_pass"] or (identity["applicable"] and identity["pass"] and final_identity["pass"] and protocol["pass"] and all(core[key]["pass"] for key in source_core)), "protocol_coverage_pass requires a matched, verified, completed source protocol")
    completion_possible = all_core_pass and critical_ok and execution["pass"] and alignment["pass"] and protocol["pass"] and paper_ok
    require(not final["task_completion_pass"] or completion_possible, "task_completion_pass conflicts with unresolved core evidence, artifact, execution, alignment, or protocol gaps")
    require(not final["scientific_validity_pass"] or not execution["unsupported_claims"], "scientific_validity_pass conflicts with unsupported claims")
    require(not final["overall_pass"] or not final["required_fixes"], "overall_pass conflicts with unresolved required_fixes; optional improvements belong in a separate field")
    require(not final["overall_pass"] or (final["scientific_validity_pass"] and final["task_completion_pass"] and completion_possible), "overall_pass requires scientific validity and task completion with no unresolved core gaps")
    result.update(completion=final["overall_pass"], task_completion=final["task_completion_pass"],
                  scientific_validity_claimed=final["scientific_validity_pass"], protocol_coverage=final["protocol_coverage_pass"],
                  missing_artifacts=sorted(path for path in expected_artifacts if not checks[path]["present"]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "start", "config", "doctor", "check"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--workspace", type=Path, required=True)
        if command == "check":
            sub.add_argument("--phase", choices=("plan", "final"), required=True)
    args = parser.parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    try:
        if args.command == "init":
            result = init_workspace(workspace)
        elif args.command == "start":
            result = start_workspace(workspace)
        else:
            profile = load_profile(workspace)
            if args.command == "config":
                result = profile
            elif args.command == "doctor":
                result = doctor(workspace, profile)
            else:
                result = check_workspace(workspace, args.phase)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 2 if args.command == "doctor" and not result["ok"] else 0
    except (ContractError, OSError, TypeError, UnicodeError) as exc:
        print(json.dumps({"structurally_valid": False, "completion": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
