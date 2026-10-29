# Primary-source register and future integrations

## Live-source targets (Phase 1)

| Coverage | Primary URL | Access | Dates / caveats |
|---|---|---|---|
| VWCE official product page | https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating | Public page | As-of date may be monthly; page top-ten holdings are **not** a complete download. |
| VFEA official product page | https://www.vanguard.co.uk/professional/product/etf/equity/9678/ftse-emerging-markets-ucits-etf-usd-accumulating | Public page | Check official monthly update date, not crawler time. |
| Vanguard official full holdings API | https://www.vanguard.co.uk/gpx/graphql | Public GraphQL interface observed in community integration code; live verification pending | Validated `portId` and ISIN on each paginated request; archive raw records and SHA-256. |

## Institutional intelligence (Phase 2, *not yet implemented*)

| Coverage | Primary URL | Rules |
|---|---|---|
| US 13F information tables | https://www.sec.gov/edgar/search/ | Filing date ≠ quarter-end; file may be amended (13F-HR/A); 45-day typical filing deadline; cover reportable long US-listed securities, not full book. |
| SEC submissions API | https://data.sec.gov/submissions/ | Resolve CIK explicitly. Follow SEC fair-access terms and declare a real contact address before automated usage. |
| SEC companyfacts | https://data.sec.gov/api/xbrl/companyfacts/ | Fundamentals require unit scaling, period normalization and restatement checks. |
| SEC Form 4 insider reports | https://www.sec.gov/edgar/search/ | Distinguish open-market buys from option awards, grants and automatic plans. |
| Manager letters | Official manager sites and fund communications | Quotes, publication dates and authorship must be verified. |
| FTSE Russell index changes | https://research.ftserussell.com/ | Index constituents and review announcements must be checked separately from Vanguard ETF positions. |

Secondary sources such as WhaleWisdom and Dataroma are useful discovery tools but **not** the system of record. Financial statements and institutional trades have disclosure delays; neither a 13F nor an ETF entry is a buy signal.

## Acceptance criteria before calling any scheduled feed production-ready

- First live Vanguard API collection succeeds for both named ISINs, full row count and as-of date.
- Second *distinct official date* exists for each ETF; manual review of at least five matched rows and all alleged additions/removals.
- 13F: amendment handling; unit/share verification against source XML; no position inferred when amendments are partial.
- Security master: locally tested stable ISIN/SEDOL/CUSIP joins with conflicts quarantined.
- Institutional intelligence and thesis reports: every factual statement linked to issuer/SEC source and date; total-return benchmark methodology agreed before any performance claim.