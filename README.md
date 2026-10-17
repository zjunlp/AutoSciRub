<p align="center">
  <img src="assets/logo.png" alt="AutoSciRub logo" width="360" />
</p>

<h1 align="center">AutoSciRub</h1>

<p align="center">
  Learning to Evaluate Before Improving: Automatic Rubric Induction for Automatic Research Agents
</p>

<p align="center">
  Turn underspecified scientific research instructions into executable rubrics for guided execution, verification, and targeted revision.
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2608.31076"><img src="https://img.shields.io/badge/Paper-arXiv-b31b1b" alt="arXiv paper" /></a>
  <a href="https://huggingface.co/papers/2608.31076"><img src="https://img.shields.io/badge/Paper-Hugging%20Face-FFD21E" alt="Hugging Face paper" /></a>
  <img src="https://img.shields.io/badge/Framework-AutoSciRub-2563EB" alt="Framework: AutoSciRub" />
  <img src="https://img.shields.io/badge/Hosts-Codex%20%7C%20Claude%20Code%20%7C%20OpenClaw-22A06B" alt="Hosts: Codex, Claude Code, and OpenClaw" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22A06B" alt="MIT license" /></a>
</p>

AutoSciRub is a plugin bundle for AI research agents. It packages the workflow from the paper
[Learning to Evaluate Before Improving: Automatic Rubric Induction for Automatic Research Agents](https://arxiv.org/abs/2608.31076) as installable skills
that work across Codex, Claude Code, and OpenClaw.

The repository provides a **general-purpose research workflow** and optional
**benchmark-specific adaptations**. The general workflow turns instructions,
literature, and available data into an executable rubric. The
[ResearchClawBench adaptation](benchmarks/researchclawbench/README.md) specializes
that workflow for the benchmark's task structure, public-source protocol
recovery, and report/figure requirements, with configurable environments and
execution budgets.

The trajectories, reports, and evaluation records from our main ResearchClawBench experiments are
available on [Hugging Face](https://huggingface.co/datasets/huminclu/autoscirub-rcb-main-exp).

## News

  **2026-10-17** — Added an optional
  [ResearchClawBench skill bundle](benchmarks/researchclawbench/README.md), with
  environment setup guidance, configurable budgets, and structural evidence
  checks. See the adaptation guide for installation, provenance, and evaluation
  scope; this release has not been benchmarked.

  **2026-09-03** — AutoSciRub reached **33.2 Pass@1** with Codex + GPT-5.6-Sol
  in the September 2026
  [ResearchClawBench](https://github.com/InternScience/ResearchClawBench)
  [leaderboard snapshot](https://internscience.github.io/ResearchClawBench-Home/).

  <p align="center">
    <img src="assets/leaderboard0902.png" alt="AutoSciRub on the September 2026 ResearchClawBench leaderboard" width="100%" />
  </p>

  <p align="center">
    <em>ResearchClawBench leaderboard snapshot recorded on 2026-09-03 04:05 UTC.</em>
  </p>

  **2026-08-13** — AutoSciRub achieved **2nd place** on the
  [ResearchClawBench](https://github.com/InternScience/ResearchClawBench)
  [leaderboard](https://internscience.github.io/ResearchClawBench-Home/), with a
  **25.1 Pass@1** score using Codex + GPT-5.6-Terra.

## Highlights

- **Rubric induction at inference time** — builds a goal skeleton, grounds it in literature, and
  adapts to the data actually available in the task.
- **Executable rubric contract** — each criterion names the required analysis, evidence artifacts,
  and satisfaction condition.
- **Criterion-level verification** — verification reports which specific criteria are unmet and why,
  instead of a single score.
- **Targeted revision loop** — revisions are driven by failed criteria, not vague feedback.
- **Configurable retrieval backends** — built-in support for arXiv, OpenAlex, Semantic Scholar,
  and Tavily through a single script and a shared YAML config.
- **General-purpose default workflow** — adapts to your research project's paths,
  data, and prepared environments; optional bundles make benchmark-specific
  conventions explicit.

## Choose a workflow

| Workflow | Intended use | What it provides |
| --- | --- | --- |
| **General AutoSciRub** (default) | Research projects with their own instructions, data, and output conventions | Eight skills for rubric induction, literature grounding, data exploration, execution guidance, verification, and targeted revision |
| **[ResearchClawBench adaptation](benchmarks/researchclawbench/README.md)** | ResearchClawBench task workspaces | Six specialized skills for instruction/source evidence mapping, complete experimental comparisons, report and figure verification, and bounded repair |

Both use the same rubric-guided research approach. Adaptations make a
benchmark's input/output conventions and evidence requirements explicit.
Research environments are prepared by the user; the ResearchClawBench guide
explains how to configure Python interpreter paths and task budgets. Public
task inputs and permitted literature provide the scientific context; hidden
evaluation materials are excluded.

The bundles can coexist. Select `autoscirub` for the general workflow or
`rcbench-workflow-controller` for the adaptation, and follow that controller's
configuration and artifact contract for the task.

The Quick Start below uses the general workflow. For benchmark tasks, follow
the [ResearchClawBench setup guide](benchmarks/researchclawbench/README.md).

## Quick Start

Requires **Python 3.10+** and a research agent (Codex, Claude Code, or OpenClaw).
AutoSciRub's scripts prepare and inspect a project; your agent performs the research.

### 1. Set up once

Linux / macOS:

```bash
git clone https://github.com/zjunlp/AutoSciRub.git
cd AutoSciRub
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/install.py codex  # or: claude, openclaw
```

Windows PowerShell:

```powershell
git clone https://github.com/zjunlp/AutoSciRub.git
cd AutoSciRub
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/install.py codex
```

Use this Python environment when running the helpers. In PowerShell, replace
`python` below with `.\.venv\Scripts\python.exe` if you have not activated it.

### 2. Check the offline example

```bash
python scripts/autoscirub.py demo --project ./autoscirub-demo
```

No model, API key, PDF upload, or external query is used. The demo copies a tiny
synthetic task into a new directory and checks that exactly one allowed local
document is indexed while the excluded folder is omitted. It is a setup check,
not a claim that an agent has completed the scientific task.

To try the complete workflow, open your agent in `autoscirub-demo/`
and ask: **“Use AutoSciRub to complete INSTRUCTIONS.md using local files only.”**
The sample explains its expected numerical results in
[examples/minimal/README.md](examples/minimal/README.md).

### 3. Use your own project

Run these commands from the AutoSciRub checkout:

```bash
python scripts/autoscirub.py init --project /path/to/my-research
python scripts/autoscirub.py doctor --project /path/to/my-research
```

On Windows use a quoted Windows project path. `init` creates a config without
overwriting an existing one; it does not copy or alter your research data.

Open a new agent session in your research project, using the Python environment
above if you want the bundled helpers, and give it a concrete instruction:

> Use AutoSciRub to compare treatment and control in data/measurements.csv.
> Save the analysis code, a results table, and a short report. Use local sources
> from papers/ and perform at most one revision round.

Other supported scopes:

- **Rubric only:** “Use AutoSciRub to make an executable rubric for this task. Stop before experiments.”
- **Verification only:** “Verify report.md against the existing AutoSciRub rubric. Do not revise it.”

## Installation and updates

Choose a bundle when installing; `generic` is the default:

```bash
python scripts/install.py codex                              # General workflow: eight skills
python scripts/install.py codex --bundle researchclawbench   # Benchmark adaptation: six skills
```

Replace `codex` with `claude` or `openclaw` for that host. The installer copies
the selected skills and their bundled resources into the platform's personal
skill directory. It does not register a marketplace or run the agent. These
directories follow the platform documentation:

| Platform | Personal directory | Documentation |
| --- | --- | --- |
| Codex | `.agents/skills` under your user directory | [Codex skills](https://learn.chatgpt.com/docs/build-skills) |
| Claude Code | `.claude/skills` under your user directory | [Claude skills](https://code.claude.com/docs/en/skills) |
| OpenClaw | `.openclaw/skills` under your user directory | [OpenClaw skills](https://docs.openclaw.ai/tools/skills) |

Preview or check an installation:

```bash
python scripts/install.py codex --dry-run
python scripts/install.py codex --check
python scripts/install.py codex --bundle researchclawbench --check
```

`--check` verifies the installed files against this checkout. To verify
actual discovery, open a new agent session and ask it to list the AutoSciRub
skills. Agent policy or workspace-level overrides can still affect availability.

After updating your checkout, rerun the installer. Identical files are left
alone. Previously installed, unmodified skills are updated; locally edited or
unmanaged same-name skills cause an actionable error before any skill is changed.
For a custom location, use `--skills-dir` and configure your agent to load it.

The Bash and PowerShell wrappers call the same installer:
`./scripts/install.sh codex` or `./scripts/install.ps1 codex`.
Select the adaptation with Bash's `--bundle researchclawbench` or PowerShell's
`-Bundle researchclawbench`. PowerShell also accepts `-Check`, `-DryRun`, and
`-SkillsDir`.

Existing marketplace users may continue using the plugin package. Avoid enabling
both that plugin and the personal copies simultaneously. The manifests remain in
`plugins/autoscirub/`; the personal-skill installer does not update an existing
plugin cache.

## Configuration

This section describes the general workflow. The ResearchClawBench adaptation
uses a separate `.rcbench/profile.yaml`; see its
[configuration and environment guide](benchmarks/researchclawbench/README.md).

`init` creates `PROJECT/.autoscirub/config.yaml`. YAML is parsed with PyYAML;
the same JSON Schema validates both partial overrides and the resolved settings.
Comments, quoted strings, lists, and anchors are supported. Duplicate keys,
unknown fields, misspelled provider names, and invalid types fail before retrieval.
YAML merge keys that create duplicate keys are rejected; use explicit sections.

For local-only work, a complete minimal config is:

```yaml
retrieval:
  enabled_sources: [local_literature]
  local_literature:
    paths: [papers]
  exclusions:
    excluded_paths: [papers/private]
```

Local inputs and exclusions are exact files or directories, not glob patterns.
Directories are searched recursively; excluded subtrees and links to excluded
files are omitted. Local indexing provides filenames and paths, not full-text
search or scientific relevance ranking. It does not upload documents.

Path rules:

- `--project` selects the research root; otherwise the current directory is used.
- With no `--config`, read `PROJECT/.autoscirub/config.yaml` if it exists.
- An explicit `--config` path is relative to the shell's current directory.
- All paths *inside* the config are relative to the research root, not the config file.
- State directory precedence: `--state-dir` → `AUTOSCIRUB_STATE_DIR` → config `state_dir` → `.autoscirub`.
- Retrieval output defaults to `STATE/literature_sources.json`; `--out` overrides it.
- MinerU output defaults to `STATE/cache/mineru/`; its `--output-dir` overrides it.
- AutoSciRub skills use the same resolved state directory. Reports, code, and
  scientific results stay in the locations agreed with the user.

```bash
python scripts/autoscirub.py config validate --project /path/to/my-research
python scripts/autoscirub.py retrieve --project /path/to/my-research --query "research question"
```

Use repeatable `--query` arguments for separate queries, or `--goals` for a
rubric skeleton. Run `retrieve --help` for the complete options.
The original skill script remains directly executable.

Full defaults: [config/sources.example.yaml](config/sources.example.yaml).
The editor-facing [config/sources.schema.json](config/sources.schema.json) points
to the canonical schema bundled with the retrieval skill.

### Network services

The default config enables arXiv, OpenAlex, Semantic Scholar, and local indexing.
Tavily is opt-in: add it to `enabled_sources` and set its provider `enabled: true`.
Credentials are read only from environment variables:

| Variable | Purpose |
| --- | --- |
| `OPENALEX_EMAIL` | OpenAlex contact email |
| `OPENALEX_API_KEY` | OpenAlex access, when required by the service |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar authentication/rate allowance |
| `TAVILY_API_KEY` | Required for Tavily |
| `MINERU_API_TOKEN` | MinerU standard API |

Remote retrieval sends query text to the selected providers. MinerU is a separate,
optional converter that uploads input documents; leave it disabled for local-only
work. API access, rates, and costs are controlled by those services. `web`
means the agent's native web search, not an implemented provider in this script.

## Progress and troubleshooting

The retriever prints each source's progress and saves structured `provider_results`.

| Situation | Behavior / next step |
| --- | --- |
| Invalid configuration | Exit 2 with the field to correct; no requests made |
| Missing Python dependency | Install `requirements.txt` using the same Python executable |
| Missing local document | Check project-relative `local_literature.paths`; shown as a failed source |
| Missing required key | Source skipped with the variable name to set |
| Successful query, no usable results | Status `empty`, exit 0; try broader terms or local papers |
| Some sources fail | Status `partial`, exit 0; available sources retained with failure details |
| Every source fails or none can run | Exit 3; write `literature_sources.failure.json`, preserving the previous index |
| HTTP 401 / 403 / 429 | Check provider access or rate allowance; no automatic unbounded retries |
| Skill not available in agent | Run install `--check`, restart the agent, inspect its local skill settings |
| Installer detects local edits | Preserve your changes or choose a different configured skill directory |

A default request can wait up to 30 seconds before a network timeout. This version
uses sequential requests and reports progress; it does not automatically retry or
resume requests. `doctor` checks local configuration, dependencies, paths,
and environment-variable presence without making paid requests or testing keys.

## Workflow and state

The state files below belong to the general workflow. The ResearchClawBench
bundle has its own [artifact contract](benchmarks/researchclawbench/skills/rcbench-workflow-controller/references/contracts.md).

The controller performs seven steps: instruction goals, literature grounding,
data exploration, criterion synthesis, research execution, criterion verification,
and bounded revision. The agent runs the scientific experiments; the CLI does not
replace it. Simple tasks need only a few goals and criteria, not a fixed quota.

The default revision limit is one round (`workflow.max_revision_rounds`).
Every full-workflow revision is followed by verification. Missing inputs remain
explicit unmet requirements; `all_satisfied` cannot be true while any
in-scope criterion is unmet. Verification-only requests never authorize edits.

Framework state includes:

- `run_manifest.json`: controller-maintained task, stage, budget, and output locations.
- `rubric_skeleton.json`, `literature_grounding.json`, `task_data_profile.json`,
  and `executable_rubric.json`: planning and evidence contracts.
- `literature_sources.json`: optional helper-generated retrieval index.
- `verification_report.json` and `revisions/round-NNN/`: checks and revisions.
- `cache/mineru/`: optional converted literature.

## Development checks

```bash
python -m pip install -r requirements.txt
python scripts/validate.py
python -m unittest discover -s tests -v
```

Tests use local fixtures and mocked network responses. GitHub Actions runs them
on Linux, macOS, and Windows with Python 3.10 and 3.12, plus Bash and PowerShell
installer smoke checks. They verify helper behavior, not model reasoning quality
or live provider availability.

## Citation

If you use AutoSciRub in your research, please cite our [paper](https://arxiv.org/abs/2608.31076):

```bibtex
@article{autoscirub,
  title={Learning to Evaluate Before Improving: Automatic Rubric Induction for Automatic Research Agents},
  author={Wang, Xuehai and Qin, Haowei and Liu, Tongxin and Li, Junkai and Xu, Buqiang and Zhang, Jintian and Chen, Yijun and Xue, Zirui and Deng, Shumin},
  journal={arXiv preprint arXiv:2608.31076},
  year={2026},
  doi={10.48550/arXiv.2608.31076},
  url={https://arxiv.org/abs/2608.31076}
}
```

## License

MIT. See [LICENSE](LICENSE).
