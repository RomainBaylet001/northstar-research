"""Conservative, dated ETF equity comparison. Unknown identity => review, never a buy signal."""
from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .vanguard import IntegrityError, fingerprint


def snapshots(root, fund):
    root = Path(root)
    folder = root / "data" / "etf" / "snapshots" / fund
    groups = defaultdict(list)
    for path in sorted(folder.glob("*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("fund") != fund or record.get("official_as_of") != path.parent.name
                or record.get("source_sha256") != path.stem
                or fingerprint(record.get("raw_items", [])) != path.stem):
            raise IntegrityError("Archive integrity error: " + str(path))
        groups[path.parent.name].append((path, record))
    bad = [d for d, records in groups.items() if len(records) > 1]
    if bad:
        raise IntegrityError("Multiple official versions for " + ", ".join(bad) + "; manual adjudication required")
    return [groups[d][0] for d in sorted(groups)]


def ids(row):
    return {"ISIN:" + row["isin"]} if row.get("isin") else set() | (
        {"SEDOL:" + row["sedol"]} if row.get("sedol") else set()
    )


def keys(row):
    answer = set()
    if row.get("isin"):
        answer.add("ISIN:" + row["isin"])
    if row.get("sedol"):
        answer.add("SEDOL:" + row["sedol"])
    return answer


def allocation(rows, field):
    sums = defaultdict(lambda: Decimal("0"))
    for row in rows:
        sums[row.get(field) or "Unknown"] += Decimal(row["weight_pct"])
    return sums


def compare(old, new):
    if old["fund"] != new["fund"] or old["fund_isin"] != new["fund_isin"]:
        raise IntegrityError("Cross-fund comparison forbidden")
    if old["official_as_of"] >= new["official_as_of"]:
        raise IntegrityError("Dates must increase")
    prior, current = old["equities"], new["equities"]
    if len(prior) < 100 or len(current) < 100:
        raise IntegrityError("Unreasonably small holdings count")
    lookup_a, lookup_b = defaultdict(set), defaultdict(set)
    for i, row in enumerate(prior):
        for key in keys(row):
            lookup_a[key].add(i)
    for j, row in enumerate(current):
        for key in keys(row):
            lookup_b[key].add(j)
    edges = {(i, j) for key in lookup_a.keys() & lookup_b.keys()
             for i in lookup_a[key] for j in lookup_b[key]}
    joined_a, joined_b = defaultdict(set), defaultdict(set)
    for i, j in edges:
        joined_a[i].add(j)
        joined_b[j].add(i)
    if any(len(v) != 1 for v in joined_a.values()) or any(len(v) != 1 for v in joined_b.values()):
        raise IntegrityError("Ambiguous ISIN/SEDOL reconciliation")
    for i, j in edges:
        a, b = prior[i], current[j]
        if a.get("isin") and b.get("isin") and a["isin"] != b["isin"]:
            raise IntegrityError("Same SEDOL with different known ISINs: identity migration needs review")
    matched_a = {i for i, _ in edges}
    matched_b = {j for _, j in edges}
    un_a = [r for i, r in enumerate(prior) if i not in matched_a]
    un_b = [r for j, r in enumerate(current) if j not in matched_b]
    t_a = {r["ticker"] for r in un_a if r.get("ticker")}
    t_b = {r["ticker"] for r in un_b if r.get("ticker")}
    if t_a & t_b:
        raise IntegrityError("Unmatched holdings share a ticker: possible corporate action, review required")
    changes = []
    for i, j in sorted(edges):
        a, b = prior[i], current[j]
        delta = Decimal(b["weight_pct"]) - Decimal(a["weight_pct"])
        qa, qb = a.get("shares"), b.get("shares")
        changes.append({
            "name": b["name"], "ticker_old": a["ticker"], "ticker_new": b["ticker"],
            "isin": b["isin"] or a["isin"], "sedol": b["sedol"] or a["sedol"],
            "country": b["country"], "sector": b["sector"],
            "old_weight_pct": a["weight_pct"], "new_weight_pct": b["weight_pct"],
            "delta_bps": str(delta * 100),
            "old_shares": qa, "new_shares": qb,
            "shares_delta": str(Decimal(qb) - Decimal(qa)) if qa is not None and qb is not None else None,
        })
    additions = [dict(r, old_weight_pct="0", new_weight_pct=r["weight_pct"]) for r in un_b]
    removals = [dict(r, old_weight_pct=r["weight_pct"], new_weight_pct="0") for r in un_a]
    allocations = {}
    for name in ("country", "sector"):
        a, b = allocation(prior, name), allocation(current, name)
        allocations[name] = [{
            "name": k, "old_pct": str(a[k]), "new_pct": str(b[k]),
            "delta_bps": str((b[k] - a[k]) * 100),
        } for k in sorted(a.keys() | b.keys())]
    return {
        "status": "verified_identifier_comparison", "fund": new["fund"], "fund_isin": new["fund_isin"],
        "old_as_of": old["official_as_of"], "new_as_of": new["official_as_of"],
        "old_source": old["source_page"], "new_source": new["source_page"],
        "old_source_sha256": old["source_sha256"], "new_source_sha256": new["source_sha256"],
        "old_count": len(prior), "new_count": len(current),
        "additions": sorted(additions, key=lambda x: x["name"]),
        "removals": sorted(removals, key=lambda x: x["name"]),
        "matched_changes": sorted(changes, key=lambda x: abs(Decimal(x["delta_bps"])), reverse=True),
        "allocations": allocations,
        "unidentified_zero_weight_old": old.get("zero_weight_unidentified_equities", []),
        "unidentified_zero_weight_new": new.get("zero_weight_unidentified_equities", []),
        "limits": [
            "Unidentifiable zero-weight source records are retained in full archives but excluded from verified identity joins.",
            "ETF position additions are not necessarily additions to the underlying FTSE index.",
            "Changes in market weights combine price movement, trading, currency, and ETF flows.",
            "Fund share-count changes alone do not prove institutional accumulation.",
            "ISIN/SEDOL migrations need review; ticker or name alone never establishes identity.",
            "Vanguard country labels reflect provider classifications, not revenue exposure.",
        ],
    }


def changes_only(report):
    """Small auditable report; full official holdings stay in immutable archives."""
    columns = (
        "status", "fund", "fund_isin", "old_as_of", "new_as_of",
        "old_source", "new_source", "old_source_sha256", "new_source_sha256",
        "old_count", "new_count", "additions", "removals",
        "unidentified_zero_weight_old", "unidentified_zero_weight_new", "limits",
        "old_archive", "new_archive",
    )
    return {key: report[key] for key in columns if key in report}


def markdown(report):
    """Only report entrants/exits; never enumerate long-held unchanged positions."""
    s = [
        "# " + report["fund"] + " — verified additions and removals",
        "",
        "Official holdings dates: **" + report["old_as_of"] + " → " + report["new_as_of"] + "**",
        "",
        "Source: " + report["new_source"], "",
        "Fund ISIN: " + report["fund_isin"], "",
        "Equity positions with usable IDs: " + str(report["old_count"]) + " → " + str(report["new_count"]), "",
        "New securities: **" + str(len(report["additions"])) +
        "** · Fully removed securities: **" + str(len(report["removals"])) + "**", "",
        "Unchanged constituents and mere weight/share changes are deliberately omitted.",
        "",
    ]
    for label, heading in (("additions", "Newly added"), ("removals", "Fully removed")):
        s += ["## " + heading, "", "| Company | Ticker | ISIN | Country | Sector | Previous weight | Current weight |",
              "|---|---|---|---|---|---:|---:|"]
        for row in report[label]:
            s.append("| " + " | ".join(str(row.get(k, "") or "").replace("|", "/") for k in
                     ("name", "ticker", "isin", "country", "sector", "old_weight_pct", "new_weight_pct")) + " |")
        if not report[label]:
            s.append("| None verified | | | | | | |")
        s.append("")
    s += [
        "## Interpretation and data quality", "",
        "- Entry/exit refers to fund holdings, not necessarily FTSE benchmark constituents.",
        "- Changes can result from corporate actions, share class changes, replication, or index rebalancing.",
        "- Same-ISIN holdings remain present even when their market weight or share count changes.",
        "- Zero-weight unidentified positions remain in the original archive but are excluded from verified entries/exits.",
        "- Comparisons require two complete, independently dated official snapshots.",
        "",
        "Previous source SHA-256: " + report["old_source_sha256"], "",
        "Current source SHA-256: " + report["new_source_sha256"], "",
    ]
    return "\n".join(s) + "\n"


def latest(root, fund):
    root = Path(root)
    found = snapshots(root, fund)
    if len(found) < 2:
        return {"status": "insufficient_distinct_official_snapshots", "fund": fund,
                "available_dates": [row["official_as_of"] for _, row in found]}
    (path_a, old), (path_b, new) = found[-2:]
    report = compare(old, new)
    report["old_archive"] = path_a.relative_to(root).as_posix()
    report["new_archive"] = path_b.relative_to(root).as_posix()
    directory = root / "reports" / "etf" / fund
    directory.mkdir(parents=True, exist_ok=True)
    stem = old["official_as_of"] + "_to_" + new["official_as_of"] + "_" + old["source_sha256"][:12] + "_" + new["source_sha256"][:12]
    json_file, md_file = directory / (stem + ".json"), directory / (stem + ".md")
    if not json_file.exists():
        with json_file.open("x", encoding="utf-8") as fh:
            json.dump(changes_only(report), fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    if not md_file.exists():
        with md_file.open("x", encoding="utf-8") as fh:
            fh.write(markdown(report))
    report["report_path"] = md_file.relative_to(root).as_posix()
    return report
