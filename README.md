# NORTHSTAR Intelligence — Vanguard UCITS research infrastructure

An independent research repository. **Do not merge into `northstar-finance`** without authorization.

## Current implementation scope

Implemented: official Vanguard UK professional GPX collector for `VWCE` (port ID 9679, ISIN `IE00BK5BQT80`) and `VFEA` (port ID 9678, ISIN `IE00BK5BR733`); full cursor pagination; identity and date validation; archived immutable source rows; stable ISIN/SEDOL normalization; distinct-as-of comparisons; detailed Markdown/JSON reports; run/error logs; scheduled GitHub Actions; offline unit tests. Zero third-party dependencies.

**Status:** Source pages and API schema patterns have been researched; live API retrieval is **not verified** in the authoring environment (network/DNS unavailable). GitHub Actions' first real run is the live integration test. If it fails, logs will explain why. No backfilled or invented holdings changes. Newly published official dates may be monthly, even though the collector checks weekly.

## Commands

```bash
python -m unittest discover -s tests -v
python -m northstar collect --root .
python -m northstar compare --root .
python -m northstar status --root .
```

`collect` makes HTTPS POST requests only to `https://www.vanguard.co.uk/gpx/graphql`, archives only after complete pagination, and saves immutable `data/etf/snapshots/<ETF>/<OFFICIAL_AS_OF>/<SOURCE_SHA256>.json` files. A newly retrieved file with the same date and same contents is a no-op; a revised file with the same as-of date gets a second immutable version and **blocks further comparisons for manual review**. A new official month creates an additional dated snapshot and a full difference report in `reports/etf/<ETF>/`. A first snapshot produces a truthful insufficient-history status.

The scheduled workflow runs every **Wednesday 04:00 UTC / 09:30 IST** and may be started manually using GitHub Actions → Vanguard official holdings archive → Run workflow. Logs are committed even after partial failure; the workflow is marked failed, not green, if collection/verification fails. GitHub schedule executions can be delayed/skipped by GitHub.

## Data layers planned

```
.github/workflows/vanguard-holdings.yml     # Implemented
northstar/                                # Collector and comparison modules
  __main__.py
  vanguard.py
  compare.py
tests/                                    # Offline synthetic-data tests
data/etf/snapshots/{VWCE,VFEA}/           # Immutable official holdings
reports/etf/{VWCE,VFEA}/                  # Immutable official date comparisons
logs/runs/                                # Timestamped execution and failure records
data/institutional/                       # Phase 2: EDGAR 13F + amendments
    (future: quarterly filings indexed by CIK/accession)
data/security_master/                     # Phase 2: cross-market ID mapping
    (future: ISIN, SEDOL, CUSIP, FIGI mapping with provenance)
data/watchlist/                           # Phase 3: thesis history and outcomes
reports/investment/                       # Phase 3: analyst reviews and benchmarks
```

## Interpretation constraints

- Actual fund share changes are not evidence of active-manager accumulation. ETF issuance/redemption, corporate actions, and index tracking matter.
- Percentage weight changes are **not** proof of net share purchases; ordinary market moves can change weights.
- ISIN/SEDOL stable identity is used for comparability. No name-only matching. Ambiguous mappings and malformed source pages fail closed.
- `bloombergIsoCountry` is a Vanguard country field, not necessarily the issuer's place of incorporation or revenue geography.
- Non-equity cash and derivatives are retained in `raw_items`, not falsely counted as newly added stocks.
- An ETF holdings change is not necessarily an index constituent change; a comparison report is not a trading recommendation.
- UK site API field naming, access and rate limits can change; confirm first scheduled live run before relying on the feed.

## Primary sources

- VWCE fund: https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating
- VFEA fund: https://www.vanguard.co.uk/professional/product/etf/equity/9678/ftse-emerging-markets-ucits-etf-usd-accumulating
- Official GraphQL endpoint: https://www.vanguard.co.uk/gpx/graphql
- SEC EDGAR 13F (planned phase 2): https://www.sec.gov/edgar/search/ ; https://www.sec.gov/search-filings/edgar-application-programming-interfaces

## Initial installation

Create a **new, empty** repository named `northstar-research` in the GitHub account and grant the GitHub ChatGPT connection access to it. Import these files as the repository's initial commit. If your GitHub default branch is protected, the scheduled committer needs permission to push data to a designated data branch and the workflow must be adjusted. Workflow token needs only `contents: write`, not repo-admin or external API keys. Prefer a private repository if the watchlist or reports might contain private financial data.

**Not implemented yet:** quarterly 13F collector, manager selection, equities scoring, valuation scenario engine, return benchmarking, or automated LLM research. The Vanguard collector does not magically perform those tasks. They belong in separate, tested phases with clear source provenance.