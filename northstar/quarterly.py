"""Historical quarterly holding-ENTRY/EXIT reporting from complete verified Vanguard archives.

This module NEVER estimates missing quarter snapshots from factsheets or current holdings.
"""
from __future__ import annotations

import calendar
import json
from datetime import date
from pathlib import Path

from .compare import changes_only, compare, snapshots


def quarters_for_year(year, today=None):
    if not 2000 <= year <= 2100:
        raise ValueError("Year outside supported range")
    today = today or date.today()
    if year > today.year:
        return []
    n = 4 if year < today.year else (today.month - 1) // 3
    return [
        (f"Q{q}", f"{year}-{q*3:02d}-{calendar.monthrange(year, q*3)[1]:02d}")
        for q in range(1, n+1)
    ]


def quarterly(root, fund, year, today=None, save=True):
    """Compute only true holding entries/exits on exact calendar quarter-end dates."""
    root = Path(root)
    available = snapshots(root, fund)
    by_date = {row["official_as_of"]: (path, row) for path, row in available}
    quarters = quarters_for_year(year, today=today)
    table = [{
        "quarter": label, "required_as_of": day, "available": day in by_date,
        "archive": by_date[day][0].relative_to(root).as_posix() if day in by_date else None,
    } for label, day in quarters]
    # Adjacent periods first, with a Q1->latest full-period view when Q1 exists.
    periods = []
    for left, right in zip(table, table[1:]):
        periods.append((left, right, "adjacent"))
    if len(table) >= 3:
        periods.append((table[0], table[-1], "year_to_date"))
    comparisons = []
    for left, right, kind in periods:
        item = {"period": left["quarter"] + " → " + right["quarter"],
                "kind": kind, "from": left["required_as_of"],
                "to": right["required_as_of"]}
        if not left["available"] or not right["available"]:
            item.update(status="unverifiable_missing_complete_snapshots",
                        missing_dates=[x["required_as_of"] for x in (left, right) if not x["available"]])
        else:
            before = by_date[left["required_as_of"]][1]
            after = by_date[right["required_as_of"]][1]
            result = compare(before, after)  # fail closed on ambiguous security identity
            item.update(changes_only(result))
            item["status"] = "verified"
        comparisons.append(item)
    report = {
        "schema_version": 1, "fund": fund, "year": year,
        "publication_basis": "complete official Vanguard snapshots at exact calendar quarter ends",
        "quarters": table, "comparisons": comparisons,
        "available_archive_dates": sorted(by_date),
        "missing_quarter_dates": [p["required_as_of"] for p in table if not p["available"]],
        "historical_caveat": "Only dates whose complete original holdings are archived can be compared. Top-ten factsheets are insufficient.",
    }
    lines = [
        f"# {fund} — {year} quarterly changes only", "",
        "**Only fully new and fully removed holdings are listed.** Existing long-held stocks, even if reweighted, are omitted.",
        "",
        "## Official quarter-end coverage", "",
        "| Quarter | Required official date | Archive status |",
        "|---|---|---|",
    ]
    for p in table:
        lines.append(f'| {p["quarter"]} | {p["required_as_of"]} | {"Verified archive" if p["available"] else "Unavailable"} |')
    lines += [""]
    for item in comparisons:
        lines += ["## " + item["period"] + (" (cumulative)" if item["kind"] == "year_to_date" else ""), ""]
        if item["status"] != "verified":
            lines += [
                "Cannot verify additions/removals: complete official holdings are missing for " +
                ", ".join(item["missing_dates"]) + ".", "",
            ]
            continue
        lines += [
            "**New holdings: " + str(len(item["additions"])) +
            " · Completely removed: " + str(len(item["removals"])) + "**", "",
        ]
        for field, title in (("additions", "Added"), ("removals", "Removed")):
            lines += ["### " + title, "", "| Company | Ticker | ISIN | Country | Sector | Previous % | Current % |",
                      "|---|---|---|---|---|---:|---:|"]
            for row in item[field]:
                vals = [row.get(k, "") for k in
                        ("name", "ticker", "isin", "country", "sector", "old_weight_pct", "new_weight_pct")]
                lines.append("| " + " | ".join(str(v or "").replace("|", "/") for v in vals) + " |")
            if not item[field]:
                lines.append("| No verified changes | | | | | | |")
            lines += [""]
        lines += ["Sources: " + item["old_source"] + " · " + item["new_source"], ""]
    lines += [
        "## Integrity policy", "",
        "An addition or removal is a *holding-level* change, not proof of FTSE index membership,",
        "net fund-manager buying or investment merit. Source-file identifiers and dates are in the",
        "paired JSON report. A missing quarter is never approximated from holdings of another date or ETF.", "",
    ]
    if save:
        dest = root / "reports" / "quarterly" / fund
        dest.mkdir(parents=True, exist_ok=True)
        artifacts = [(dest / f"{year}.json", json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"),
                     (dest / f"{year}.md", "\n".join(lines))]
        for path, value in artifacts:
            if not path.exists() or path.read_text(encoding="utf-8") != value:
                path.write_text(value, encoding="utf-8")
        report["report_path"] = (dest / f"{year}.md").relative_to(root).as_posix()
    return report
