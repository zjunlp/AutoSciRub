#!/usr/bin/env python3
"""Small project helper: init, doctor, config, retrieve, and an offline demo."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL = ROOT / "plugins/autoscirub/skills/scientific-literature-grounding/scripts/retrieve_literature.py"


def initialize(project: Path, module: dict) -> None:
    module["dependencies"]()
    project.mkdir(parents=True, exist_ok=True)
    state = project / ".autoscirub"
    state.mkdir(exist_ok=True)
    config = state / "config.yaml"
    if config.exists():
        print(f"Keeping existing config: {config}")
    else:
        example = ROOT / "config/sources.example.yaml"
        with config.open("x", encoding="utf-8") as stream:
            stream.write(example.read_text(encoding="utf-8"))
        print(f"Created {config}")
    ignore = state / ".gitignore"
    if not ignore.exists():
        with ignore.open("x", encoding="utf-8") as stream:
            stream.write("*\n")
    module["load_config"](project=project)
    print("Next: edit retrieval.local_literature.paths if you have papers, then run doctor.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "doctor", "demo"):
        command = sub.add_parser(name)
        command.add_argument("--project", type=Path, default=Path.cwd())
    config = sub.add_parser("config", help="Validate project config without network access")
    config.add_argument("action", choices=["validate"])
    config.add_argument("--project", type=Path, default=Path.cwd())
    config.add_argument("--config", type=Path)
    sub.add_parser("retrieve", add_help=False, help="Retrieve literature; use retrieve --help for options")
    # Delegate retrieval parsing intact, including its --help.
    arguments = list(sys.argv[1:] if argv is None else argv)
    module = runpy.run_path(str(RETRIEVAL))
    if arguments and arguments[0] == "retrieve":
        return module["main"](arguments[1:])
    args = parser.parse_args(arguments)
    project = args.project.expanduser().resolve()
    try:
        if args.command == "init":
            initialize(project, module)
        elif args.command == "config":
            forwarded = ["--project", str(project), "--validate-config"]
            if args.config:
                forwarded += ["--config", str(args.config)]
            return module["main"](forwarded)
        elif args.command == "doctor":
            cfg = module["load_config"](project=project)
            if not project.is_dir():
                raise ValueError(f"Project not found: {project}. Run init first.")
            selected = module["discover_config"](project)
            print(f"Python: {sys.executable}\nConfig: {selected or 'built-in defaults'}\nState: {cfg['state_dir']}")
            parent = Path(cfg["state_dir"])
            while not parent.exists():
                parent = parent.parent
            if not parent.is_dir() or not os.access(parent, os.W_OK):
                raise ValueError(f"State directory is not writable: {cfg['state_dir']}")
            for path in cfg["retrieval"]["local_literature"]["paths"]:
                if not (project / Path(path).expanduser()).exists():
                    raise ValueError(f"Missing local literature: {path}")
            for name in cfg["retrieval"]["enabled_sources"]:
                provider = cfg["retrieval"]["providers"].get(name, {})
                key_name = provider.get("api_key_env")
                if key_name and provider.get("enabled", True):
                    key_set = bool(module["get_env"](key_name))
                    print(f"{name}: {key_name} {'set' if key_set else 'not set'}")
                    if name == "tavily" and not key_set:
                        raise ValueError(f"Set {key_name} or disable Tavily before retrieval.")
            for agent in ("codex", "claude", "openclaw"):
                print(f"{agent}: {'on PATH' if shutil.which(agent) else 'not on PATH'}")
            print("Local checks passed. No network/API authentication or agent skill discovery was tested.")
            print("Check installed files separately: python scripts/install.py PLATFORM --check")
        elif args.command == "demo":
            module["dependencies"]()
            # Use a new directory; never mix sample fixtures into existing research.
            if project.exists() and any(project.iterdir()):
                raise ValueError("Demo needs an empty directory. Use --project ./autoscirub-demo")
            project.mkdir(parents=True, exist_ok=True)
            for source in (ROOT / "examples/minimal").iterdir():
                target = project / source.name
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
            initialize(project, module)
            # The sample is an offline document-index smoke test, not an LLM run.
            config = project / ".autoscirub/config.yaml"
            config.write_text((project / "offline.yaml").read_text(encoding="utf-8"), encoding="utf-8")
            result = module["main"](["--project", str(project), "--query", "compare treatment and control"])
            if result:
                return result
            cfg = module["load_config"](project=project)
            output = json.loads((Path(cfg["state_dir"]) / "literature_sources.json").read_text(encoding="utf-8"))
            if len(output["all_sources"]) != 1 or output["all_sources"][0]["title"] != "methods.md":
                raise ValueError("Demo failed: expected exactly one allowed local document.")
            print("Offline demo passed: allowed paper indexed, excluded folder omitted.")
            print(f"To try the research workflow, open your agent in {project} and ask: "
                  "Use AutoSciRub to complete INSTRUCTIONS.md using local files only.")
        return 0
    except (module["ConfigError"], OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
