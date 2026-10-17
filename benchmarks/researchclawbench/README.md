# AutoSciRub — ResearchClawBench Adaptation

This optional bundle adapts AutoSciRub to ResearchClawBench's task inputs,
paper-grounded experiments, and report/figure deliverables. It is based on
`skills-0901-r2`, with portable configuration, explicit execution states and
structural checks. The generic AutoSciRub bundle remains the default.

The research agent performs the scientific work. Installation, configuration,
retrieval and structural validation helpers do not run the experiments or call
the benchmark judge.

## Install

Use Python 3.10+ and run these commands from the AutoSciRub checkout, in a Python
environment where you can install the helper dependencies:

```bash
python -m pip install -r requirements.txt
python scripts/install.py codex --bundle researchclawbench
python scripts/install.py codex --bundle researchclawbench --check
```

Replace `codex` with `claude` or `openclaw` for that host. For a custom directory,
add `--skills-dir YOUR_SKILLS_DIRECTORY` and configure your host to load it.
The installer checks the whole bundle before updating and refuses to overwrite
unmanaged or locally edited skills. `--dry-run` previews the destinations.

The Bash wrapper accepts the same arguments. The PowerShell wrapper uses:

```powershell
./scripts/install.ps1 codex -Bundle researchclawbench
./scripts/install.ps1 codex -Bundle researchclawbench -Check
```

The six skills are `rcbench-workflow-controller`, `rcbench-instruction-rubric`,
`rcbench-grounding-research`, `rcbench-experiments-design`,
`rcbench-report-verifier` and `rcbench-mineru-pdf-to-markdown`. The last name
avoids replacing the generic `mineru-pdf-to-markdown` skill. Both bundles can be
installed together; explicitly select the RCBench controller for a benchmark
task so the agent follows one workflow and artifact contract.

## Prepare and select your Python environments

The original experiments used three locally prepared virtual environments.
Their binaries and machine-specific paths are **not distributed** with this
bundle. Prepare the environments needed by your tasks, then replace the
interpreter paths in the workspace's `.rcbench/profile.yaml`.

| Environment role | Typical use | Packages used in the historical environment family |
| --- | --- | --- |
| `base` | Arrays, tables, statistics and plots | NumPy, pandas, SciPy, Matplotlib, scikit-learn, statsmodels, h5py |
| `ml` | Neural models, multimodal, chemistry and materials | Base stack plus task-appropriate PyTorch/CUDA, transformers, accelerate; RDKit, ASE or pymatgen when needed |
| `bio_geo` | Single-cell and geospatial data | Base stack plus anndata/scanpy or geopandas/shapely/rasterio when needed |

These are environment roles, not fixed domain-to-environment assignments or a
complete reproducibility lockfile. Use the task's implementation requirements
to select dependency versions. CUDA, GPU memory, model weights, system libraries
and data availability remain machine- and task-dependent. Existing Conda or
virtual environments are also supported by recording their Python executable.

For example, create a CPU analysis environment outside the immutable task data:

```bash
python -m venv .venv-rcb-base
.venv-rcb-base/bin/python -m pip install -r requirements.txt
.venv-rcb-base/bin/python -m pip install numpy pandas scipy matplotlib scikit-learn statsmodels h5py
```

On Windows use `.venv-rcb-base\Scripts\python.exe` in place of
`.venv-rcb-base/bin/python`. Prepare additional environments only for tasks that
need them; select PyTorch and accelerator packages for your actual hardware and
the research implementation. The helper dependencies are PyYAML and jsonschema;
they do not provision the scientific software stack.

After initializing a workspace, edit its profile, for example:

```yaml
default_environment: base
environments:
  base:
    python: /path/to/your/.venv-rcb-base/bin/python
    description: General scientific analysis
  ml:
    python: /path/to/your/.venv-rcb-ml/bin/python
    description: Task-specific deep learning and materials dependencies
  bio_geo:
    python: /path/to/your/.venv-rcb-bio-geo/bin/python
    description: Task-specific single-cell and geospatial dependencies
```

Replace these example paths with your own. A relative interpreter path is
relative to the task workspace; a bare command such as `python` is resolved on
`PATH`. A Windows YAML value can use single quotes, for example
`'C:\research\envs\base\Scripts\python.exe'`. An absolute path is useful when
many independent workspaces share the same environment. Do not copy or commit
the environment directory into a skill.

The agent records its selected environment in `outputs/refined_rubric.json` and
performs the relevant import and small computation checks before expensive work.
`doctor` checks interpreter availability, not package imports, GPU readiness or
API authentication. For a prepared base environment, a manual check is:

```bash
/path/to/your/.venv-rcb-base/bin/python -c "import numpy, pandas, scipy, matplotlib; print('imports ok')"
```

## Initialize a task

Prepare a task workspace containing `INSTRUCTIONS.md`, `data/` and optional
`related_work/`, using the benchmark harness. Keep the hidden evaluator files
outside the agent's accessible workspace. From the AutoSciRub checkout:

```bash
python benchmarks/researchclawbench/skills/rcbench-workflow-controller/scripts/rcbench.py init --workspace /path/to/task-workspace
```

Edit `.rcbench/profile.yaml` to select your prepared environments, providers and
budgets, then check the configuration and record the run's starting state:

```bash
python benchmarks/researchclawbench/skills/rcbench-workflow-controller/scripts/rcbench.py doctor --workspace /path/to/task-workspace
python benchmarks/researchclawbench/skills/rcbench-workflow-controller/scripts/rcbench.py config --workspace /path/to/task-workspace
python benchmarks/researchclawbench/skills/rcbench-workflow-controller/scripts/rcbench.py start --workspace /path/to/task-workspace
```

The same helper is included in the installed controller skill. `init` creates
`.rcbench/profile.yaml` without replacing existing configuration. `start` writes
`outputs/rcbench_run_manifest.json` after preparation and preserves an existing
run's provenance. The manifest identifies the adapter version, historical source and actual
skill/configuration contents; it is not evidence that research is complete.

Open a new agent session in that workspace and ask:

> Use rcbench-workflow-controller to complete INSTRUCTIONS.md with the
> ResearchClawBench adaptation. Use my prepared environments and budgets in
> .rcbench/profile.yaml. Save the report to report/report.md and run the final
> structural check after scientific verification.

This request authorizes execution and the configured bounded repair loop. For
planning or verification alone, say so explicitly; verification alone does not
authorize revisions.

## Configuration and retrieval

The canonical defaults are bundled in
[profile.yaml](skills/rcbench-workflow-controller/references/profile.yaml).
Use the project profile to configure:

- initial and followup query limits, full-text reading and revision budgets;
- report figure budget and selected research environment;
- enabled literature providers, per-provider request limits, timeouts and
  environment-variable names for credentials;
- local literature paths and exclusions.

Defaults retain the historical compact budget: three initial queries, one
followup, two new full texts, seven final figures and one revision round. These
are resource limits, not target counts or permission to omit required science.
If a limit prevents completion, record the gap and budget exhaustion; changing a
budget must be explicit and recorded. A source paper's scope cannot silently
override the task's requested scope.

Retrieval supports local literature, arXiv, OpenAlex, Semantic Scholar, Tavily
and SciAtlas. It saves candidates and query/provider provenance. Set credentials
in your shell or secret manager using the configured environment-variable
names; personal credential-file paths are not embedded in the skills. Provider
access is optional and depends on the user's accounts. Do not put actual keys
in the YAML. For offline work, set `retrieval.enabled_sources` to
`[local_literature]` and point its paths at the supplied literature.

From the task workspace, use the installed or checkout skill directory:

```bash
python /path/to/skills/rcbench-grounding-research/scripts/retrieve_literature.py --config .rcbench/profile.yaml --query-plan outputs/retrieval_query_plan.json
```

The helper rejects oversized query plans and reused query IDs with changed
text. Initial/followup limits and `retrieval.limits.max_queries_per_task` are
independent caps; adjust both when deliberately increasing the overall budget.
Per-provider query limits apply cumulatively across resumed requests;
`--resume` does not silently expand a provider's budget. Failed requests remain
visible and are not retried automatically. A provider with exhausted capacity
skips remaining queries and records this in `budget_usage`; an explicitly
increased budget can admit new queries. Total retrieval failure returns a
nonzero status and retains the prior successful output. The trace documents
provider failures; an agent's candidate labels are not ground-truth retrieval
accuracy measurements. Local literature is indexed once under a separate
`local` attempt, so individual query counters can be zero during a successful
local-only run; this index is not full-text relevance search.

MinerU is optional when existing text is insufficient. It may upload documents
to an external conversion service; choose local extraction for local-only work.
Its cache is `artifacts/literature/pdf_markdown/`, leaving `data/` and
`related_work/` unchanged.

## Evidence contract and checks

The workflow preserves instruction requirements, relevant public-source result
blocks, complete comparison matrices, generated evidence and report references.
The verifier independently re-enumerates the required evidence from raw
instructions and inspected public sources; this is a review procedure, not a
claim that a separate model process is automatically launched.

Detailed artifacts and JSON fields are in
[contracts.md](skills/rcbench-workflow-controller/references/contracts.md).
Planning uses `planned` rather than claiming completed experiments. Execution
states are `planned`, `in_progress`, `partial`, `pass` and `blocked`. Missing
inputs remain explicit gaps. Literature numbers remain reference values, and
correctly obtained results may disagree with them.

Scientific validity, task completion, protocol coverage and paper identity are
recorded separately. An instruction-led task can be complete without identifying
a unique source paper. Once a relevant source protocol is explicitly adopted,
its applicable core requirements cannot be removed to obtain a passing result.

Run structural checks from any directory:

```bash
python /path/to/skills/rcbench-workflow-controller/scripts/rcbench.py check --workspace /path/to/task-workspace --phase plan
python /path/to/skills/rcbench-workflow-controller/scripts/rcbench.py check --workspace /path/to/task-workspace --phase final
```

The helper checks references, states, required files and pass-flag consistency.
An honest partial report can be structurally valid while remaining incomplete.
Exit code 0 means structural validation passed; inspect the reported completion
fields. A structural pass does not establish method correctness, execution
authenticity, statistical validity or a benchmark score. The agent still needs
to inspect code, measured results and critical figures.

Essential evidence belongs in `report/report.md` and final `report/images/`.
The benchmark judge does not automatically follow report links to arbitrary
local result files. No helper calls the judge or reads hidden checklists,
`target_study/`, other tasks' runs or private evaluator feedback. A file being
present does not make it an authorized research input.

## Version and evaluation scope

Adapter version: **0.1.0**. Historical source: **skills-0901-r2**.
[provenance.json](provenance.json) records the source repository commit, original
file hashes and renamed skill. The published adaptation changes configuration,
completion semantics and helper behavior; it has **not been benchmarked**.
The source repository's MIT notice is retained in [SOURCE_LICENSE](SOURCE_LICENSE);
the AutoSciRub repository's [MIT license](../../LICENSE) also covers this release.

The paper and historical leaderboard results linked from the
[main README](../../README.md) describe earlier experiment runs. Public
trajectories, reports and evaluation records from the main experiments are
available in the [experiment archive](https://huggingface.co/datasets/huminclu/autoscirub-rcb-main-exp).
Those results are not measurements of this portable adaptation. Report new
results with the adapter version, research and judge models, scoring mode,
task set, budgets, retries, report selection and score aggregation.

## Development validation

From the AutoSciRub checkout:

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
```

Tests use temporary workspaces and mocked or local inputs. They validate
installation, configuration, retrieval and structural invariants, not live
service availability or research quality. The repository CI includes the
optional bundle's installer checks on Linux, macOS and Windows.
