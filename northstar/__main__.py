"""CLI for dated official Vanguard holdings collection and comparisons."""
from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .compare import latest, snapshots
from .quarterly import quarterly
from .vanguard import FUNDS, collect, now, store


def run(argv=None, fetch=None):
    parser = argparse.ArgumentParser(description="NORTHSTAR Vanguard research")
    parser.add_argument("command", choices=("collect", "compare", "status", "quarterly"))
    parser.add_argument("--year", type=int, default=datetime.now(timezone.utc).year,
                        help="Calendar year for quarterly comparison (defaults to UTC current year)")
    parser.add_argument("--fund", choices=("VWCE", "VFEA", "all"), default="all")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    names = list(FUNDS) if args.fund == "all" else [args.fund]
    log = {"start_utc": now(), "operation": args.command, "events": [], "errors": []}
    for name in names:
        try:
            if args.command == "collect":
                snap = collect(name, fetch=fetch) if fetch else collect(name)
                file, is_new = store(snap, root)
                log["events"].append({
                    "fund": name, "status": "archived" if is_new else "already_archived",
                    "official_as_of": snap["official_as_of"], "rows": snap["total_holdings"],
                    "archive": file.relative_to(root).as_posix(),
                })
            if args.command == "quarterly":
                result = quarterly(root, name, args.year)
                log["events"].append({
                    "fund": name, "quarterly_report": result.get("report_path"),
                    "year": args.year, "missing_quarter_dates": result["missing_quarter_dates"],
                    "pairs": [{
                        "period": p["period"], "status": p["status"],
                        "added": len(p.get("additions", [])), "removed": len(p.get("removals", [])),
                    } for p in result["comparisons"]],
                })
            else:
                if args.command == "status":
                    result = {
                        "fund": name, "status": "history",
                        "dates": [record["official_as_of"] for _, record in snapshots(root, name)],
                    }
                else:
                    result = latest(root, name)
                log["events"].append({
                    "fund": name, "comparison": {k: v for k, v in result.items()
                                                 if k not in ("additions", "removals", "matched_changes", "allocations")},
                    "added": len(result.get("additions", [])), "removed": len(result.get("removals", [])),
                })
        except Exception as error:
            log["errors"].append({
                "fund": name, "type": type(error).__name__,
                "message": str(error), "trace": traceback.format_exc(limit=3),
            })
    log["end_utc"] = now()
    folder = root / "logs" / "runs"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with (folder / (stamp + ".json")).open("x", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps(log, ensure_ascii=False, indent=2))
    return int(bool(log["errors"]))


if __name__ == "__main__":
    raise SystemExit(run())
