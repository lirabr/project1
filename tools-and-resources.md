# Tool and resource catalog

Install only what a working phase uses. No vendor choice or cost estimate guarantees access, suitability, data rights or profitable performance. Confirm current availability and pricing before purchase.

## Required now

| Resource | Purpose | Verification / boundary |
|---|---|---|
| Python 3.12 + uv | Reproducible runtime | `uv sync --locked --python 3.12 --extra dev --extra graph`; `uv.lock` pins resolved packages |
| Git + editor | Source/config review | Local repository optional for reading pack; needed for release identities and CI |
| pandas / NumPy / PyArrow | Features and Parquet | Already dependencies; synthetic offline tests |
| scikit-learn | HGB and training transforms | Already dependency; no GPU or PyTorch required |
| yfinance | Convenience daily history | Already dependency; network only for download; not an execution feed or PIT guarantee |
| SQLite with FTS5 | Episodes and prototype book | Python bundled SQLite; tests exercise FTS and temporary databases |
| pytest / Ruff | Regression and lint | `uv run --no-sync pytest -q`; `uv run --no-sync ruff check src tests` |
| LangGraph + SQLite checkpointer | Optional checkpoint/approval demonstration | `graph` extra; not required for direct `cycle` |

The lockfile was generated under a release cutoff of 2026-09-15 UTC. Keep this reproducible cutoff until a reviewed dependency refresh; do not relax it to make a build pass. Install tooling through trusted package managers. ML libraries/model pickle formats can execute code when loaded: accept serialized artifacts only from verified trusted builds.

## Optional later, with an adoption condition

| Resource | Earliest useful stage | Adoption condition / work required |
|---|---|---|
| MLflow (`tracking` extra) | Phase 1 | Need experiment UI; does not replace immutable manifests, saved models or promotion policy |
| PIT/corporate-action data vendor and exchange calendars | Phase 1/4 | Data validity or venue parity required; evaluate rights, survivorship, timestamp semantics, outages and revisions |
| Broker SDK (one venue first) | Phase 4 | Adapter contract and tests exist; add reviewed pinned dependency with paper/live separation |
| Secret manager / OS keychain | Before external credentials | Named operator, access policy, rotation/revocation test; no secrets in prompts/logs/backups |
| PostgreSQL | Phase 2/4 when needed | Transactional multi-writer reservations/migrations require it; implement adapters and recovery, not just containers |
| Object storage | Phase 4/5 | Off-host evidence/backups, encryption, retention and trusted audit anchors |
| Scheduler / service manager | Phase 4/5 | Market-aware cadence, single-flight, restart/reconcile behavior; cron alone is not safe execution control |
| Metrics/alerting and remote error reporting | Phase 4/5 | Operator will actually receive and respond to tested alerts; redact payloads |
| pgvector / Qdrant | Phase 5 | Measured retrieval latency/size bottleneck and evaluated relevance; raw cosine quality must be fixed first |
| LLM provider | Phase 3 optional | Provider/key/egress binding, typed output and cost controls; measurable utility over deterministic reports |
| SBOM/dependency/security scanning | Before certified release | Scan locked Python packages, source, container images if adopted, and repository history for accidentally committed secrets |

TimescaleDB, Redis, Docker, CrewAI, additional cloud accounts, news/social scrapers, and on-chain feeds are not prerequisites. Each increases operations, licensing, security and evaluation work. Avoid a second dataframe engine or orchestration framework without a demonstrated need.

## Budget and access worksheet

Before spending, record an owner-approved monthly ceiling for data, LLM, hosting/storage and monitoring, plus a separate capital-at-risk limit. Subscription budgets and trading-loss limits are different controls.

Capture for each provider: legal/account eligibility, intended use/redistribution rights, historical depth, timezone/availability semantics, rate limits, retries/backoff, data/export retention rights, key scope, region restrictions, outage procedure and cancellation terms. Set hard API spend limits where supported. No exact commercial prices are assumed in this pack.

## Official references checked during review

- [uv installation](https://docs.astral.sh/uv/getting-started/installation/) and [resolution / release cutoffs](https://docs.astral.sh/uv/concepts/resolution/).
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/durable-execution): checkpoint state and cross-thread memory are different; in-memory savers cannot survive process restart. Follow the currently linked checkpointer documentation for API details matching the lockfile.
- [Alpaca paper trading](https://docs.alpaca.markets/docs/paper-trading): paper execution does not model all market impact, latency slippage, queue position, fees or dividends; paper/live credentials differ.

These are engineering references, not endorsements of a venue, asset or strategy. Research code and untrusted feed text never receive broker authority.

## Pack maintenance tools

From the outer `project1-v3` directory:

```bash
python3 tools/project_pack.py verify-source ../project1-v2
python3 tools/project_pack.py bundle
python3 tools/validate_pack.py
```

The source manifest inventories every original file, including the original ZIP and Finder metadata. Import verified the original ZIP's files against the expanded source. Runtime artifacts, local environments, credentials and caches are intentionally excluded from the new starter archive. The historical conversation remains unmodified as provenance, not current instructions.
