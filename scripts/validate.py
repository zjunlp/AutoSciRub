#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "autoscirub"
SKILLS_ROOT = PLUGIN_ROOT / "skills"
ABS_PATH_PATTERNS = [
    re.compile(r"(^|[^A-Za-z0-9_])(\/disk\/|\/home\/|\/root\/|\/tmp\/)"),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"~\/"),
]
LEGACY_TOKENS = ["legacy-benchmark-", "legacy-workspace", "fixed-local-path"]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_no_forbidden_text(path: Path) -> None:
    text = read_text(path)
    for token in LEGACY_TOKENS:
        if token in text:
            fail(f"{path} contains forbidden token {token!r}")
    for pattern in ABS_PATH_PATTERNS:
        if pattern.search(text):
            fail(f"{path} contains a fixed absolute path pattern")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = read_text(path)
    if not text.startswith("---\n"):
        fail(f"{path} missing YAML frontmatter")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        fail(f"{path} malformed YAML frontmatter")
    frontmatter = parts[1].strip().splitlines()
    data: dict[str, str] = {}
    for line in frontmatter:
        if not line.strip():
            continue
        if ":" not in line:
            fail(f"{path} invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def validate_skill(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        fail(f"missing SKILL.md in {skill_dir}")
    fm = parse_frontmatter(skill_md)
    name = fm.get("name")
    desc = fm.get("description")
    if not name:
        fail(f"{skill_md} missing frontmatter name")
    if not desc:
        fail(f"{skill_md} missing frontmatter description")
    if skill_dir.name != name:
        fail(f"{skill_md} name {name!r} does not match folder {skill_dir.name!r}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        fail(f"{skill_md} has invalid skill name {name!r}")
    text = read_text(skill_md)
    if "[TODO:" in text or "[TODO]" in text:
        fail(f"{skill_md} still contains TODO placeholders")
    check_no_forbidden_text(skill_md)
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if openai_yaml.exists():
        yaml_text = read_text(openai_yaml)
        if "display_name:" not in yaml_text:
            fail(f"{openai_yaml} missing display_name")
        if "short_description:" not in yaml_text:
            fail(f"{openai_yaml} missing short_description")
        if "default_prompt:" not in yaml_text:
            fail(f"{openai_yaml} missing default_prompt")
        if f"$${name}" in yaml_text:
            fail(f"{openai_yaml} contains malformed skill reference")
        check_no_forbidden_text(openai_yaml)


def validate_json(path: Path) -> dict:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"{path} invalid JSON: {exc}")


def validate_plugin_manifest() -> None:
    manifest = validate_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    required = ["name", "version", "description", "author", "skills", "interface"]
    for key in required:
        if key not in manifest:
            fail(f"codex manifest missing {key}")
    if manifest["name"] != "autoscirub":
        fail("codex manifest name must be autoscirub")
    if "hooks" in manifest:
        fail("codex manifest must not include hooks")
    check_no_forbidden_text(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    claude = validate_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
    for field in ("name", "version", "homepage", "repository", "skills"):
        if claude.get(field) != manifest.get(field):
            fail(f"plugin manifests disagree on {field}")

    interface = manifest["interface"]
    for key in ["displayName", "shortDescription", "longDescription", "developerName", "category", "defaultPrompt"]:
        if key not in interface:
            fail(f"codex manifest interface missing {key}")


def validate_schema_files() -> None:
    from jsonschema import Draft202012Validator
    schema_dirs = [PLUGIN_ROOT / "schemas", ROOT / "config",
                   SKILLS_ROOT / "scientific-literature-grounding/references"]
    for schema_dir in schema_dirs:
        for schema_path in sorted(schema_dir.glob("*.schema.json")):
            Draft202012Validator.check_schema(validate_json(schema_path))
            check_no_forbidden_text(schema_path)


def validate_example_config() -> None:
    retrieval_script = SKILLS_ROOT / "scientific-literature-grounding" / "scripts" / "retrieve_literature.py"
    module = runpy.run_path(str(retrieval_script))
    example = read_text(ROOT / "config" / "sources.example.yaml")
    parsed = module["read_yaml"](example)
    config = module["deep_merge"](module["DEFAULT_CONFIG"], parsed)
    module["validate_config"](config)
    module["validate_config"](parsed)

    enabled_sources = parsed.get("retrieval", {}).get("enabled_sources")
    if not isinstance(enabled_sources, list) or not enabled_sources:
        fail("example config enabled_sources must parse as a non-empty list")


def validate_marketplace(path: Path) -> None:
    marketplace = validate_json(path)
    if "name" not in marketplace or "plugins" not in marketplace:
        fail(f"{path} missing marketplace root fields")
    if not marketplace["plugins"]:
        fail(f"{path} must contain at least one plugin entry")
    entry = marketplace["plugins"][0]
    if entry.get("name") != "autoscirub":
        fail(f"{path} plugin entry must be autoscirub")
    if path.parent.name == ".claude-plugin":
        if not marketplace.get("owner", {}).get("name"):
            fail("Claude marketplace requires an owner")
        if entry.get("source") != "./plugins/autoscirub":
            fail("Claude marketplace source must be relative to the repository root")
        return
    policy = entry.get("policy") or {}
    for key in ["installation", "authentication"]:
        if key not in policy:
            fail(f"{path} plugin policy missing {key}")
    if "category" not in entry:
        fail(f"{path} plugin entry missing category")


def validate_rcbench() -> None:
    """Validate the optional bundle without installing it or starting research."""
    import yaml
    from jsonschema import Draft202012Validator

    root = ROOT / "benchmarks/researchclawbench"
    skills = root / "skills"
    installer = runpy.run_path(str(ROOT / "scripts/install.py"))
    actual = {p.name for p in skills.iterdir() if p.is_dir()}
    if actual != installer["RCBENCH_SKILLS"]:
        fail("ResearchClawBench bundle is incomplete")
    for skill in sorted(skills.iterdir()):
        if not skill.is_dir():
            continue
        validate_skill(skill)
        for path in sorted(skill.rglob("*")):
            if path.is_file() and path.suffix in {".md", ".yaml", ".json"}:
                check_no_forbidden_text(path)
                if path.name.endswith(".schema.json"):
                    Draft202012Validator.check_schema(validate_json(path))
                if path.suffix == ".md":
                    for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", read_text(path)):
                        link = link.split("#", 1)[0]
                        if link and "://" not in link and not (path.parent / link).is_file():
                            fail(f"{path} contains a missing local reference: {link}")
    references = skills / "rcbench-workflow-controller/references"
    profile = yaml.safe_load(read_text(references / "profile.yaml"))
    schema = validate_json(references / "profile.schema.json")
    Draft202012Validator(schema).validate(profile)
    provenance = validate_json(root / "provenance.json")
    if provenance.get("source_bundle") != "skills-0901-r2":
        fail("ResearchClawBench provenance must name the historical source bundle")
    if provenance.get("adaptation_version") != profile.get("adaptation_version"):
        fail("ResearchClawBench profile and provenance versions disagree")
    hashes = provenance.get("source_file_sha256", {})
    if not hashes or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()):
        fail("ResearchClawBench provenance is missing historical source hashes")


def main() -> None:
    validate_plugin_manifest()
    validate_marketplace(ROOT / ".agents" / "plugins" / "marketplace.json")
    validate_marketplace(ROOT / ".claude-plugin" / "marketplace.json")
    validate_schema_files()
    validate_example_config()
    for skill_dir in sorted(p for p in SKILLS_ROOT.iterdir() if p.is_dir()):
        validate_skill(skill_dir)
    validate_rcbench()
    print("validation ok")


if __name__ == "__main__":
    main()
