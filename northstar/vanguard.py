"""Official Vanguard UCITS holdings collector. No top-ten or inferred-data fallbacks."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://www.vanguard.co.uk/gpx/graphql"
FUNDS = {
    "VWCE": {
        "port_id": "9679",
        "isin": "IE00BK5BQT80",
        "page": "https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating",
    },
    "VFEA": {
        "port_id": "9678",
        "isin": "IE00BK5BR733",
        "page": "https://www.vanguard.co.uk/professional/product/etf/equity/9678/ftse-emerging-markets-ucits",
    },
}
QUERY = """query NorthstarHoldings($ids:[String!]!, $cursor:String) {
 funds(portIds:$ids) { profile { portId fundFullName identifiers(altIds:["ISIN"]) { altId altIdValue } } }
 borHoldings(portIds:$ids) { holdings(limit:1500,lastItemKey:$cursor) {
   items { isin sedol1 issuerName securityLongDescription ticker securityType
     marketValuePercentage quantity effectiveDate gicsSectorDescription
     icbSectorDescription bloombergIsoCountry }
   totalHoldings lastItemKey
 } }
}"""


class IntegrityError(RuntimeError):
    """Untrusted, incomplete, or ambiguous source data."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(rows):
    # Sorting removes network pagination/order noise without changing the underlying records.
    return hashlib.sha256(canonical(sorted(rows, key=lambda x: canonical(x)))).hexdigest()


def request_graphql(endpoint, payload, attempts=3):
    body = canonical(payload)
    headers = {
        "Content-Type": "application/json", "Accept": "application/json",
        "x-consumer-id": "uk2", "User-Agent": "NORTHSTAR-Research/1.0 (public holdings archive)",
    }
    for attempt in range(attempts):
        try:
            with urlopen(Request(endpoint, data=body, headers=headers, method="POST"), timeout=35) as resp:
                raw = resp.read(12_000_001)
                if len(raw) > 12_000_000:
                    raise IntegrityError("Oversized API response")
                return json.loads(raw)
        except HTTPError as exc:
            if exc.code not in (408, 425, 429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except (URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
        time.sleep(2 ** attempt)
    raise IntegrityError("Vanguard request retries exhausted")


def amount(x, label):
    try:
        n = Decimal(str(x))
        if not n.is_finite():
            raise ValueError("nonfinite")
        return n
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise IntegrityError("Invalid " + label) from exc


def normalize(raw):
    """Equities only; full raw source is retained separately including cash/derivatives."""
    grouped = {}
    aliases = {}
    for h in raw:
        typ = str(h.get("securityType") or "").upper()
        if not typ.startswith("EQ."):
            continue
        isin = str(h.get("isin") or "").strip().upper()
        sedol = str(h.get("sedol1") or "").strip().upper()
        if isin and not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
            raise IntegrityError("Malformed equity ISIN")
        if sedol and not re.fullmatch(r"[A-Z0-9]{7}", sedol):
            raise IntegrityError("Malformed equity SEDOL")
        if not isin and not sedol:
            raise IntegrityError("Equity has neither ISIN nor SEDOL")
        weight = amount(h.get("marketValuePercentage"), "weight")
        if weight < 0 or weight > 100:
            raise IntegrityError("Out of range weight")
        qty = h.get("quantity")
        shares = None if qty in (None, "") else amount(qty, "quantity")
        name = str(h.get("issuerName") or h.get("securityLongDescription") or "").strip()
        if not name:
            raise IntegrityError("Unnamed equity")
        key = "ISIN:" + isin if isin else "SEDOL:" + sedol
        if sedol:
            previous = aliases.setdefault(sedol, isin)
            if previous and isin and previous != isin:
                raise IntegrityError("SEDOL reused with conflicting ISINs")
        record = {
            "id": key, "isin": isin, "sedol": sedol, "name": name,
            "ticker": str(h.get("ticker") or ""), "country": str(h.get("bloombergIsoCountry") or ""),
            "sector": str(h.get("gicsSectorDescription") or h.get("icbSectorDescription") or ""),
            "security_type": typ, "weight_pct": str(weight),
            "shares": None if shares is None else str(shares),
        }
        if key not in grouped:
            grouped[key] = record
        else:
            old = grouped[key]
            old["weight_pct"] = str(amount(old["weight_pct"], "prior weight") + weight)
            old["shares"] = str(amount(old["shares"], "prior shares") + shares) if shares is not None and old["shares"] is not None else None
            for field in ("name", "ticker", "country", "sector", "sedol"):
                if old[field] != record[field]:
                    old[field] = ""
    out = sorted(grouped.values(), key=lambda x: x["id"])
    if len(out) < 100:
        raise IntegrityError("Too few equity holdings for a complete fund")
    total = sum((amount(r["weight_pct"], "weight") for r in out), Decimal(0))
    if not Decimal("85") <= total <= Decimal("105"):
        raise IntegrityError("Equity weight sum indicates incomplete holdings: " + str(total))
    return out


def collect(fund, fetch=request_graphql):
    if fund not in FUNDS:
        raise ValueError("Unknown fund")
    cfg = FUNDS[fund]
    cursor, visited, rows, total = None, set(), [], None
    for _ in range(40):
        reply = fetch(URL, {
            "operationName": "NorthstarHoldings", "query": QUERY,
            "variables": {"ids": [cfg["port_id"]], "cursor": cursor},
        })
        if not isinstance(reply, dict) or reply.get("errors") or not isinstance(reply.get("data"), dict):
            raise IntegrityError("Vanguard GraphQL error or missing data")
        data = reply["data"]
        funds, holdings = data.get("funds"), data.get("borHoldings")
        if not isinstance(funds, list) or len(funds) != 1 or not isinstance(holdings, list) or len(holdings) != 1:
            raise IntegrityError("Ambiguous ETF identity or holdings page")
        profile = (funds[0] or {}).get("profile") or {}
        ids = {i.get("altIdValue") for i in (profile.get("identifiers") or []) if i.get("altId") == "ISIN"}
        if str(profile.get("portId")) != cfg["port_id"] or cfg["isin"] not in ids:
            raise IntegrityError("Unexpected fund ID or ISIN")
        page = (holdings[0] or {}).get("holdings") or {}
        n = page.get("totalHoldings")
        if type(n) is not int or not 100 <= n <= 100_000 or total is not None and n != total:
            raise IntegrityError("Invalid or changing totalHoldings")
        total = n
        batch = page.get("items")
        if not isinstance(batch, list) or not 1 <= len(batch) <= 1500 or any(not isinstance(x, dict) for x in batch):
            raise IntegrityError("Invalid holdings batch")
        rows.extend(batch)
        if len(rows) > total:
            raise IntegrityError("More rows than advertised")
        next_cursor = page.get("lastItemKey")
        if not next_cursor:
            if len(rows) != total:
                raise IntegrityError(f"Incomplete holdings pagination ({len(rows)} of {total})")
            break
        if not isinstance(next_cursor, str) or next_cursor in visited:
            raise IntegrityError("Repeated pagination cursor")
        visited.add(next_cursor)
        cursor = next_cursor
    else:
        raise IntegrityError("Pagination exceeded 40 pages")
    dates = set()
    for row in rows:
        if not isinstance(row.get("effectiveDate"), str):
            raise IntegrityError("Missing holdings effective date")
        try:
            d = date.fromisoformat(row["effectiveDate"][:10])
        except ValueError as exc:
            raise IntegrityError("Invalid holdings date") from exc
        dates.add(d.isoformat())
    if len(dates) != 1:
        raise IntegrityError("Mixed official snapshot dates")
    official_date = dates.pop()
    if date.fromisoformat(official_date) > datetime.now(timezone.utc).date():
        raise IntegrityError("Future official snapshot date")
    return {
        "schema_version": 1, "fund": fund, "fund_isin": cfg["isin"],
        "official_as_of": official_date, "retrieved_utc": now(),
        "source_page": cfg["page"], "source_endpoint": URL, "total_holdings": total,
        "source_sha256": fingerprint(rows), "raw_items": rows, "equities": normalize(rows),
    }


def store(snapshot, root):
    """Write each distinct official file version to its own content-hash path."""
    path = Path(root) / "data" / "etf" / "snapshots" / snapshot["fund"] / snapshot["official_as_of"] / (snapshot["source_sha256"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        prior = json.loads(path.read_text(encoding="utf-8"))
        if fingerprint(prior.get("raw_items", [])) != snapshot["source_sha256"]:
            raise IntegrityError("Corrupt existing archive")
        return path, False
    with path.open("x", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, sort_keys=True, indent=2)
        file.write("\n")
    return path, True
