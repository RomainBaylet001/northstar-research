"""August→September 2026 ETF holdings comparison, strict ISIN reconciliation.

August: historical Vanguard-derived Excel offered by Rebalix on 2026-10-29.
September: primary Vanguard complete archive already in NORTHSTAR main.
This script makes NO changes to production archives or reports.
"""
from __future__ import annotations
import hashlib
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from northstar.vanguard import FUNDS, IntegrityError, normalize, fingerprint
from northstar.compare import compare

NS={"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXPECTED={
    "VWCE": {"prefix":"e600d68927dc45e3", "rows":4093},
    "VFEA": {"prefix":"09a85c37a0a7d676", "rows":2360},
}
HEADERS=["Name","ISIN","Ticker","Type","Sector","Country","Currency","Weight %","Market value"]

def table_excel(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zipf:
        sheet="xl/worksheets/sheet1.xml"
        if sheet not in zipf.namelist():
            raise IntegrityError("Unexpected spreadsheet structure")
        root=ET.fromstring(zipf.read(sheet))
        rows=[]
        for row in root.findall(".//x:sheetData/x:row",NS):
            values={}
            for cell in row.findall("x:c",NS):
                col=re.match(r"[A-Z]+",cell.get("r") or "").group(0)
                v=cell.find("x:v",NS)
                inline=cell.find("x:is",NS)
                value=(v.text if v is not None else
                       "".join(inline.itertext()) if inline is not None else "") or ""
                values[col]=value.strip()
            rows.append([values.get(chr(65+i),"") for i in range(9)])
        return rows

for fund in FUNDS:
    isin=FUNDS[fund]["isin"]
    url="https://rebalix.com/api/etf/composizione?"+urlencode({"isin":isin,"lang":"en"})
    with urlopen(Request(url,headers={"User-Agent":"NORTHSTAR-Research/1.0"}),timeout=35) as response:
        cd=response.headers.get("Content-Disposition","")
        body=response.read(4_000_000)
    sha=hashlib.sha256(body).hexdigest()
    if "2026-08-31" not in cd or not sha.startswith(EXPECTED[fund]["prefix"]):
        raise IntegrityError(f"Rebalix source drift or wrong as-of date for {fund}: {cd} {sha}")
    rows=table_excel(body)
    if rows[0]!=HEADERS or len(rows)-1!=EXPECTED[fund]["rows"]:
        raise IntegrityError(f"Unexpected {fund} header/size: {rows[0]} rows {len(rows)}")
    raw=[]
    for row in rows[1:]:
        name,isin_r,ticker,typ,sector,country,currency,weight,_=row
        raw.append({
            "issuerName":name, "isin":isin_r, "sedol1":"", "ticker":ticker,
            "securityType":typ, "gicsSectorDescription":sector,
            "bloombergIsoCountry":country, "marketValuePercentage":weight,
            "effectiveDate":"2026-08-31",
        })
    stats={}
    stats["source_rows"]=len(raw)
    stats["types"]={}
    for row in raw:stats["types"][row["securityType"]]=stats["types"].get(row["securityType"],0)+1
    stats["positive_equities_without_isin"]=[
        {"name":r["issuerName"],"ticker":r["ticker"],"weight":r["marketValuePercentage"]}
        for r in raw
        if str(r["securityType"]).startswith("EQ.") and not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]",r["isin"])
        and float(r["marketValuePercentage"] or "0")>0
    ][:8]
    try:
        old_eq=normalize(raw)
    except IntegrityError as exc:
        print(json.dumps({"fund":fund,"status":"quarantined_old_normalization","error":str(exc),"stats":stats}))
        continue
    archived=list(Path("data/etf/snapshots").joinpath(fund,"2026-09-30").glob("*.json"))
    if len(archived)!=1:raise IntegrityError("Expected exactly one September official snapshot")
    new=json.loads(archived[0].read_text())
    if new["fund_isin"]!=isin or fingerprint(new["raw_items"])!=new["source_sha256"]:
        raise IntegrityError("Invalid September archived primary source")
    old={
        "fund":fund, "fund_isin":isin, "official_as_of":"2026-08-31",
        "source_page":url, "source_sha256":sha, "equities":old_eq,
        "zero_weight_unidentified_equities":[],
    }
    # An unchanged security normally keeps its ISIN. But a few corporate
    # actions/venue changes can retain a ticker or name while changing ISIN.
    # Quarantine ONLY unmatched potential migration pairs; never count them
    # as either a new entry or an exit.
    old_ids={r["isin"] for r in old_eq if r["isin"]}
    new_ids={r["isin"] for r in new["equities"] if r["isin"]}
    old_un=[r for r in old_eq if r["isin"] not in new_ids]
    new_un=[r for r in new["equities"] if r["isin"] not in old_ids]
    old_tickers={r["ticker"].strip().upper() for r in old_un if r["ticker"].strip()}
    new_tickers={r["ticker"].strip().upper() for r in new_un if r["ticker"].strip()}
    ticker_conflicts=old_tickers & new_tickers
    def clean_name(row):
        import unicodedata
        name=unicodedata.normalize("NFKC",row["name"]).casefold()
        return "".join(ch for ch in name if ch.isalnum())
    old_names={clean_name(r) for r in old_un if clean_name(r)}
    new_names={clean_name(r) for r in new_un if clean_name(r)}
    name_conflicts=old_names & new_names
    def ambiguous(r):
        return (bool(r["ticker"].strip()) and r["ticker"].strip().upper() in ticker_conflicts) or clean_name(r) in name_conflicts
    ambiguous_old=[r for r in old_un if ambiguous(r)]
    ambiguous_new=[r for r in new_un if ambiguous(r)]
    if len(ambiguous_old)+len(ambiguous_new)>80:
        raise IntegrityError("Too many ambiguous corporate-action or cross-listing pairs to infer entries safely")
    old_clean=dict(old,equities=[r for r in old_eq if r not in ambiguous_old])
    new_clean=dict(new,equities=[r for r in new["equities"] if r not in ambiguous_new])
    try:
        changes=compare(old_clean,new_clean)
    except IntegrityError as exc:
        print(json.dumps({"fund":fund,"status":"quarantined_identity_diff","error":str(exc),"stats":stats,
                          "old_equity_identifiers":len(old_eq),"new_equity_identifiers":len(new["equities"]),
                          "ticker_conflicts":sorted(ticker_conflicts)[:40]}))
        continue
    report={"fund":fund,"status":"verified_august_september_isin_comparison",
            "source_august":url, "source_august_sha256":sha,
            "source_september":archived[0].as_posix(),
            "august_equity_ids":len(old_eq), "september_equity_ids":len(new["equities"]),
            "identity_ambiguities_excluded":{"old":len(ambiguous_old),"new":len(ambiguous_new),
                "tickers":sorted(ticker_conflicts)[:40],
                "previous":[{"name":r["name"],"ticker":r["ticker"],"isin":r["isin"]} for r in ambiguous_old[:20]],
                "current":[{"name":r["name"],"ticker":r["ticker"],"isin":r["isin"]} for r in ambiguous_new[:20]]},
            "added":len(changes["additions"]), "removed":len(changes["removals"]),
            "entries":[{"name":x["name"],"ticker":x["ticker"],"isin":x["isin"],
                        "country":x["country"],"sector":x["sector"],"weight_pct":x["new_weight_pct"]}
                      for x in sorted(changes["additions"],key=lambda x:float(x["new_weight_pct"]),reverse=True)[:70]],
            "exits":[{"name":x["name"],"ticker":x["ticker"],"isin":x["isin"],
                      "weight_pct":x["old_weight_pct"]}
                     for x in sorted(changes["removals"],key=lambda x:float(x["old_weight_pct"]),reverse=True)[:35]],
            "stats":stats}
    print(json.dumps(report,ensure_ascii=False))
