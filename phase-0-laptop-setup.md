# Phase 0 — Reproducible laptop

**Goal:** a clean, testable local research environment. No Docker, broker account, LLM key, GPU, or cloud service is required. See [roadmap](roadmap.md) for dependencies and gate ownership.

## Inputs, tools, outputs

Input: this pack and a supported Python 3.12 interpreter. Output: locked environment, isolated tests, local CLI, and recorded operating decisions. Practical starting hardware: 8 GB RAM and 10 GB free storage for this small daily universe; more history/models require measuring actual disk and memory usage. A GPU is not useful for the included models.

Install Git, an editor, Python 3.12, and uv. On macOS with Homebrew already installed:

```bash
brew install git uv
uv python install 3.12
```

Other platforms: follow the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/). Use WSL2 or Linux for the shell examples. Check installer contents/publisher rather than blindly piping an unknown script into a shell. Docker is optional, not a phase gate.

## Step-by-step

1. Keep `project1-v2` unchanged. Work inside `project1-v3/trading-desk`, or copy/extract the supplied starter into its own working directory. The outer pack contains the authoritative guides; the nested starter contains code/config/tests.
2. Open a terminal in the starter. Install exactly the locked dependencies:

   ```bash
   uv --version
   uv sync --locked --python 3.12 --extra dev --extra graph
   uv run --no-sync python -V
   uv run --no-sync desk-research --help
   ```

3. Verify locally, without keys or downloaded prices:

   ```bash
   uv run --no-sync pytest -q
   uv run --no-sync ruff check src tests
   ```

   Tests use temporary state and forbid network connections. Dependency installation itself requires package-index access; that does not make tests network-dependent. `--no-sync` preserves the installed optional extras.

4. Choose version-control root. Recommended: initialize Git in `trading-desk` if using its included CI workflow. If versioning the outer pack instead, deliberately relocate/configure CI paths; GitHub does not discover a workflow nested below `trading-desk/.github`. Do not publish or push as part of setup without separate approval.
5. Check `.gitignore` before creating any secret file. `.env.example` is a historical optional integration template, not a required configuration. The CLI does **not** automatically load `.env`; leave all keys blank. Start without one.
6. Record owner, reviewer, allowed universe, data source rights, working hours, project capacity, budget ceiling, experiment success definition, and where evidence/backups live. Treat unknowns as blockers for later phases, not assumptions.
7. Read [architecture boundaries](trading-agents-architecture.md) and [acceptance tests](testing-and-acceptance.md). The package supports research and toy internal-paper behavior, not an external broker.

## Optional components, explicitly deferred

- `uv sync --locked --extra dev --extra graph --extra tracking` adds MLflow. It is not needed to run tests or generate YAML tear sheets. Run `uv run --no-sync mlflow ui --backend-store-uri data/artifacts/mlruns` only after runs exist.
- The inherited Compose file is a local infrastructure experiment, not connected to the application. Do not start it as part of Phase 0. Before adopting it, pin image digests, configure secrets and health checks, bind services to loopback/private interfaces, and implement/test actual database adapters.
- Broker SDKs, `ccxt`, `psycopg`, and Redis clients are **not** installed by the starter. There are no smoke steps that assume they are present. Add a reviewed, pinned adapter dependency only when its implementation is scheduled.

## Failures and recovery

| Symptom | Action |
|---|---|
| `uv` missing | Reopen the terminal after installation and verify PATH; use the documented installer for your OS |
| Python 3.13/3.14 selected | Run sync with `--python 3.12`; project deliberately supports 3.12 only until CI validates another version |
| Graph tests skipped | Install both `dev` and `graph`; do not report a skipped graph suite as full verification |
| Tests change a real artifact | Stop and fix fixture isolation; tests must never consume or modify operator state |
| Missing parquet | Expected before Phase 1; setup tests do not require downloaded data |
| Lock mismatch | Inspect dependency/config change and regenerate in a reviewed dependency update; do not bypass the lock or release-age cutoff |

## Exit gate

- [ ] Fresh Python 3.12 environment installed from `uv.lock`.
- [ ] Unit tests and lint pass with graph tests present.
- [ ] CLI help works; no secret or broker account needed.
- [ ] Original pack preserved; version-control/CI root chosen.
- [ ] Owner, budget, capacity, reviewer requirement, and evidence location recorded.

Next: [Phase 1](phase-1-research-lab.md). Phase 0 proves reproducibility, not trading safety.
