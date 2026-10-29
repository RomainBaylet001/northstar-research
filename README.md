# NORTHSTAR Intelligence — Vanguard UCITS research infrastructure

An independent research repository. **Do not merge into `northstar-finance`** without authorization.

## Current implementation scope

Implemented: official Vanguard UK professional GPX collector for `VWCE` (port ID 9679, ISIN `IE00BK5BQT80`) and `VFEA` (port ID 9678, ISIN `IE00BK5BR733`); full cursor pagination; identity and date validation; archived immutable source rows; stable ISIN/SEDOL normalization; distinct-as-of comparisons; concise additions/removals-only Markdown/JSON reports; run/error logs; scheduled GitHub Actions; offline unit tests. Zero third-party dependencies.

**Live integration status (29 October 2026): PASSED on GitHub-hosted runners.** The official API returned 4,235 rows for VWCE and 2,382 for VFEA, both dated 30 September 2026. One zero-weight legacy Hanergy row in each fund has no usable ISIN/SEDOL: both are retained in raw sources and explicitly excluded from verified equity joins. Synthetic test records are never committed as real holdings. Production archive commits begin only after merge. Comparison reports require two distinct official snapshot dates.

## Commands

```bash
python -m unittest discover -s tests -v
python -m northstar collect --root .
python -m northstar compare --root .
python -m northstar quarterly --year 2026 --root .
python -m northstar status --root .
```

`collect` makes HTTPS POST requests only to `https://www.vanguard.co.uk/gpx/graphql`, archives only after complete pagination, and saves immutable `data/etf/snapshots/<ETF>/<OFFICIAL_AS_OF>/<SOURCE_SHA256>.json` files. A newly retrieved file with the same date and same contents is a no-op; a revised file with the same as-of date gets a second immutable version and **blocks further comparisons for manual review**. A new official month creates an additional dated snapshot and an additions/removals-only difference report in `reports/etf/<ETF>/`. A first snapshot produces a truthful insufficient-history status.

The scheduled workflow runs every **Wednesday 04:00 UTC / 09:30 IST** and may be started manually using GitHub Actions → Vanguard holdings — archive and verify → Run workflow. Logs are committed even after partial failure; the workflow is marked failed, not green, if collection/verification fails. GitHub schedule executions can be delayed/skipped by GitHub.

## 2026 quarterly trial: Q1 / Q2 / Q3

Quarter-end targets are **2026-03-31, 2026-06-30 and 2026-09-30**. The production archive started in October 2026, and currently holds only the official **2026-09-30** holdings for both ETFs. Previous quarters **cannot be reconstructed from current API responses**, factsheet top tens, or another Vanguard fund.

Run `python -m northstar quarterly --year 2026 --root .` to create `reports/quarterly/VWCE/2026.md` and `reports/quarterly/VFEA/2026.md`. Missing complete quarter-end files are clearly labeled **unverifiable**; the program never fills them with synthetic data. If source-verified complete Q1/Q2 archives are later obtained and normalized using the same validated schema, the reports will show **only new holdings and complete exits** for Q1→Q2, Q2→Q3, and cumulative Q1→Q3. Unchanged positions and weight changes are deliberately excluded from human-facing reports and compact comparison JSON. Full raw snapshots retain all securities.

Vanguard's official passive ETF holdings disclosure policy normally publishes complete month-end holdings with a 15-calendar-day lag. It does not promise historical downloads to the public. The correct research request for a historical backfill is **complete official holdings for each specific fund and as-of date** with stable securities identifiers; do not use only the 10 largest holdings.

## Data layers planned

```
.github/workflows/vanguard-holdings.yml     # Implemented
northstar/                                # Collector and comparison modules
  __main__.py
  vanguard.py
  compare.py
tests/                                    # Offline synthetic-data tests
data/etf/snapshots/{VWCE,VFEA}/           # Immutable official holdings
reports/etf/{VWCE,VFEA}/                  # Immutable additions/removals-only comparisons
reports/quarterly/{VWCE,VFEA}/           # Exact-quarter status and compact differences
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

## Deployment and permissions

The separate repository `RomainBaylet001/northstar-research` is already created. Merge the Phase 1 pull request after both the offline tests and read-only live API probe pass. A push to `main` triggers initial production collection; afterward the workflow runs weekly (and supports manual dispatch). The live probe uses `contents: read`; the scheduled collector alone uses `contents: write`. A GitHub Actions bot commit will not recursively trigger itself.

Archive contents include public fund data only. The repository is currently PUBLIC; do not commit any personal holdings, credentials, or proprietary research. GitHub Actions access and default-branch settings must permit the collection job to push. The next full snapshot date may be monthly rather than weekly.


**Not implemented yet:** quarterly 13F collector, manager selection, equities scoring, valuation scenario engine, return benchmarking, or automated LLM research. The Vanguard collector does not magically perform those tasks. They belong in separate, tested phases with clear source provenance.