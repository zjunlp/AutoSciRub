# AutoSciRub

AutoSciRub is a local plugin bundle for scientific agents. It packages the workflow described in the paper:

1. rubric skeleton induction
2. scientific literature grounding
3. task-data exploration
4. criterion synthesis
5. criterion-level verification
6. targeted revision

It is organized as a plugin repository so it can be installed into Codex, Claude Code, or OpenClaw from the same source tree.

## Layout

- `plugins/autoscirub/` - installable plugin payload
- `plugins/autoscirub/skills/` - AutoSciRub skills
- `plugins/autoscirub/schemas/` - JSON schemas for state files
- `.agents/plugins/marketplace.json` - Codex marketplace entry
- `.claude-plugin/marketplace.json` - Claude-compatible marketplace entry
- `scripts/` - install and validation helpers

## Install

Run the helper for the target platform:

```bash
./scripts/install.sh codex
./scripts/install.sh claude
./scripts/install.sh openclaw
```

On Windows PowerShell:

```powershell
.\scripts\install.ps1 codex
.\scripts\install.ps1 claude
.\scripts\install.ps1 openclaw
```

## Validate

```bash
python3 scripts/validate.py
```

## State

AutoSciRub uses `.autoscirub/` in the current project by default. Set `AUTOSCIRUB_STATE_DIR` to override the state directory when needed.
