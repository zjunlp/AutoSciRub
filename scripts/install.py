#!/usr/bin/env python3
"""Install all AutoSciRub skills into a platform's personal skill directory."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plugins/autoscirub/skills"
MARKER = ".autoscirub-install.json"
EXPECTED_SKILLS = {
    "autoscirub", "rubric-skeleton-induction", "scientific-literature-grounding",
    "task-data-exploration", "criterion-synthesis", "criterion-level-verification",
    "targeted-revision", "mineru-pdf-to-markdown",
}


def destination(platform: str) -> Path:
    return Path.home() / {"codex": ".agents", "claude": ".claude", "openclaw": ".openclaw"}[platform] / "skills"


def inventory(folder: Path) -> dict[str, str]:
    files = {}
    for path in sorted(folder.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == MARKER:
            continue
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink in skill: {path}")
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def install(target: Path, *, check=False, dry_run=False) -> None:
    sources = sorted(p for p in SOURCE.iterdir() if p.is_dir())
    if {p.name for p in sources} != EXPECTED_SKILLS:
        raise ValueError("Source package is incomplete; restore the eight AutoSciRub skills before installing.")
    plans = []
    # Preflight the entire bundle before modifying any skill.
    for source in sources:
        expected = inventory(source)
        if "SKILL.md" not in expected:
            raise ValueError(f"Missing SKILL.md: {source}")
        dest = target / source.name
        if dest.with_name(dest.name + ".autoscirub-backup").exists():
            raise ValueError(f"Previous update backup found for {dest}. Recover or move it aside before retrying.")
        if dest.is_symlink():
            raise ValueError(f"Existing skill is a symlink: {dest}. Choose --skills-dir or move it aside yourself.")
        current = inventory(dest) if dest.is_dir() else {}
        if check:
            if current != expected:
                raise ValueError(f"Missing or out-of-date skill: {dest}. Rerun the installer.")
            continue
        if dest.exists() and current != expected:
            marker = dest / MARKER
            if not marker.is_file():
                raise ValueError(f"Existing unmanaged skill: {dest}. Choose --skills-dir or move it aside yourself.")
            recorded = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(recorded, dict) or recorded.get("files") != current:
                raise ValueError(f"Locally edited skill: {dest}. Preserve your edits before updating.")
        plans.append((source, dest, expected, current == expected))
    if check:
        print(f"Verified all {len(sources)} skills and bundled resources in {target}")
        print("File verification only. Open a new agent session and ask it to list the AutoSciRub skills.")
        return
    if dry_run:
        for _, dest, _, same in plans:
            print(f"{'Unchanged' if same else 'Install/update'}: {dest}")
        return
    target.mkdir(parents=True, exist_ok=True)
    for source, dest, expected, same in plans:
        if same:
            continue
        with tempfile.TemporaryDirectory(prefix=".autoscirub-stage-", dir=target) as temporary:
            staging = Path(temporary) / source.name
            shutil.copytree(source, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (staging / MARKER).write_text(json.dumps({"files": expected}, indent=2) + "\n", encoding="utf-8")
            # Keep rollback data outside temporary cleanup if restoration fails.
            backup = dest.with_name(dest.name + ".autoscirub-backup")
            if dest.exists():
                dest.rename(backup)
            try:
                staging.rename(dest)
            except OSError:
                if backup.exists():
                    backup.rename(dest)
                raise
            if backup.exists():
                shutil.rmtree(backup)
    install(target, check=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=["codex", "claude", "openclaw"])
    parser.add_argument("--skills-dir", type=Path, help="Override the platform's personal skills directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Verify installed files without changes")
    mode.add_argument("--dry-run", action="store_true", help="Preview destinations without changes")
    args = parser.parse_args(argv)
    try:
        target = (args.skills_dir or destination(args.platform)).expanduser().absolute()
        if target.resolve() == SOURCE.resolve() or SOURCE.resolve() in target.resolve().parents:
            raise ValueError("Installation destination must be outside the source skills tree.")
        install(target, check=args.check, dry_run=args.dry_run)
        if not args.check and not args.dry_run:
            print("Next: use the Python environment with requirements.txt installed, restart your agent, "
                  "and ask: Use AutoSciRub on my research task.")
            if not shutil.which(args.platform):
                print(f"Note: {args.platform} is not on PATH; install or open that agent before using the skills.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Installation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
