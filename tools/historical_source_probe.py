"""Read-only public historical Vanguard source discovery. No archived facts are invented."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URLS = {
    "wayback_cdx_vwce": "https://web.archive.org/cdx/search/cdx?url=www.vanguard.co.uk%2Fprofessional%2Fproduct%2Fetf%2Fequity%2F9679%2F%2A&output=json&filter=statuscode%3A200&from=202608&to=202610&collapse=timestamp%3A6&fl=timestamp%2Coriginal%2Cstatuscode",
    "wayback_cdx_vfea": "https://web.archive.org/cdx/search/cdx?url=www.vanguard.co.uk%2Fprofessional%2Fproduct%2Fetf%2Fequity%2F9678%2F%2A&output=json&filter=statuscode%3A200&from=202608&to=202610&collapse=timestamp%3A6&fl=timestamp%2Coriginal%2Cstatuscode",
    "etf_overlap_july": "https://www.etf-overlap.com/overlap/ssac-vs-vwce/",
    "etftrace_july": "https://etftrace.com/fund/vwce",
    "companiesmarketcap_vwce": "https://companiesmarketcap.com/vanguard-ftse-all-world-ucits-etf-usd-accumulation/holdings/",
    "portfolio_terminal_vwce": "https://portfolio-terminal.com/etf/vwce/holdings",
}
HEADERS = {"User-Agent": "NORTHSTAR Research/1.0 (historical-source-verification)", "Accept": "text/html, application/json"}

for label, url in URLS.items():
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=18) as res:
            raw = res.read(3_000_000)
            charset = res.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            isins = re.findall(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b", body)
            dates = sorted(set(re.findall(r"2026-(?:07|08|09)-(?:30|31)", body)))
            asofs = re.findall(r"(?:as of|holdings as of|as at)\s+.{0,24}", body, re.I)[:4]
            print(json.dumps({"name": label, "status": res.status, "url": res.url,
                              "bytes_read": len(raw), "content_type": res.headers.get("Content-Type"),
                              "isin_occurrences": len(isins), "distinct_isins": len(set(isins)),
                              "historical_dates": dates, "asof_strings": asofs,
                              "cdx_response": body[:700] if "cdx" in label else None}))
    except (HTTPError, URLError, TimeoutError, OSError) as err:
        print(json.dumps({"name": label, "error": str(err)[:200]}))


# Check historical copies of official fund pages and complete-holdings mirrors.
from urllib.parse import quote
WAYBACK = {
    "vanguard_vwce_aug": ("20260920113925", "https://www.vanguard.co.uk/professional/product/etf/equity/9679/vanguard-ftse-all-world-ucits-etf-usd-accumulating"),
    "vanguard_vwce_jul": ("20260809141730", "https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating"),
}
for label, (stamp, url) in WAYBACK.items():
    archive_url = f"https://web.archive.org/web/{stamp}id_/{url}"
    try:
        with urlopen(Request(archive_url, headers=HEADERS), timeout=20) as res:
            raw = res.read(3_000_000)
            text = raw.decode("utf-8", errors="replace")
            positions = len(re.findall(r'holdings details|holding name|fund composition|market value|download', text, re.I))
            dates = sorted(set(re.findall(r"(?:[0-3]?[0-9]\s+(?:Jul|Aug|Sep)\s+2026)|2026-(?:07|08|09)-(?:30|31)", text, re.I)))[:15]
            links = re.findall(r'href="([^"]+)"', text)
            downloadable = [u for u in links if any(x in u.lower() for x in ("holdings", ".xlsx", ".csv", "portfolio"))][-10:]
            print(json.dumps({"archive": label, "code": res.status, "bytes": len(raw),
                              "dates": dates, "holdings_keywords": positions,
                              "download_links": downloadable[:10], "has_html": "<html" in text[:3000].lower()}))
    except Exception as err:
        print(json.dumps({"archive": label, "error": str(err)[:250]}))

CDX_URLS = {
    "companymarketcap_usd": "https://companiesmarketcap.com/vanguard-ftse-all-world-ucits-etf-usd-accumulation/holdings/",
    "companymarketcap_www": "https://www.companiesmarketcap.com/vanguard-ftse-all-world-ucits-etf-usd-accumulation/holdings/",
    "companymarketcap_eur": "https://companiesmarketcap.com/eur/vanguard-ftse-all-world-ucits-etf-usd-accumulation/holdings/",
    "companymarketcap_vfea": "https://companiesmarketcap.com/vanguard-ftse-emerging-markets-ucits-etf/holdings/",
    "etftrace": "https://etftrace.com/fund/vwce",
    "portfolio_terminal": "https://portfolio-terminal.com/etf/vwce/holdings",
}
for label, url in CDX_URLS.items():
    try:
        cdx = ("https://web.archive.org/cdx/search/cdx?url=" + quote(url, safe="") +
               "&output=json&filter=statuscode%3A200&from=202608&to=202610&collapse=timestamp%3A6&fl=timestamp%2Coriginal")
        with urlopen(Request(cdx, headers=HEADERS), timeout=17) as res:
            records = json.loads(res.read(30_000))
            print(json.dumps({"cdx_site": label, "dates": records[:9]}))
    except Exception as err:
        print(json.dumps({"cdx_site": label, "error": str(err)[:200]}))


# Rebalix has historical monthly snapshots with explicit as-of dates.
REBALIX = {
    "vwce_fund": "https://rebalix.com/en/etf/IE00BK5BQT80",
    "vwce_june_to_july": "https://rebalix.com/en/etf/IE00BK5BQT80/cronologia/2026-09",
    "vwce_july_to_august": "https://rebalix.com/en/etf/IE00BK5BQT80/cronologia/2026-10",
    "vwce_history": "https://rebalix.com/en/etf/IE00BK5BQT80/cronologia",
    "vfea_fund": "https://rebalix.com/en/etf/IE00BK5BR733",
    "vfea_july_to_august": "https://rebalix.com/en/etf/IE00BK5BR733/cronologia/2026-10",
}
for label, url in REBALIX.items():
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=18) as res:
            body = res.read(2_000_000).decode("utf-8", errors="replace")
            links = re.findall(r'href=["\']([^"\']+)["\']', body, re.I)
            extracted = [(u[:250]) for u in links if
                         any(k in u.lower() for k in (".xlsx", ".csv", "download", "holdings", "portfolio"))][:25]
            print(json.dumps({"rebalix": label, "status": res.status, "bytes": len(body),
                              "asof_dates": sorted(set(re.findall(r"2026-(?:06|07|08|09)-(?:30|31)", body)))[:15],
                              "links": extracted, "positions_of_xlsx": [m.start() for m in re.finditer(".xlsx", body)][:12],
                              "positions_of_download": [m.start() for m in re.finditer("Download the full portfolio", body, re.I)][:4]}))
    except Exception as err:
        print(json.dumps({"rebalix": label, "error": str(err)[:200]}))


# Inspect client-side Excel export wiring and any embedded source rows, without copying holdings.
for label, url in {"vwce":"https://rebalix.com/en/etf/IE00BK5BQT80",
                   "vfea":"https://rebalix.com/en/etf/IE00BK5BR733"}.items():
    try:
        with urlopen(Request(url, headers=HEADERS),timeout=18) as res:
            body=res.read(2_000_000).decode("utf-8", errors="replace")
        probes=["Download the full portfolio","full portfolio","xlsx","excel","holdings","positions",
                "portfolio", "2026-07-31","2026-08-31", "2026-09-30", "2026-07", "__next_f"]
        spans={}
        for token in probes:
            idx=body.lower().find(token.lower())
            spans[token]={"index":idx, "context":body[max(0,idx-180):idx+290] if idx>=0 else ""}
        identifiers=set(re.findall(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b",body))
        print(json.dumps({"rebalix_details":label,"bytes":len(body),"isin_distinct":len(identifiers),"snippets":spans}))
    except Exception as err:print(json.dumps({"rebalix_details":label,"error":str(err)[:200]}))


# Locate the offered published-holdings Excel link exactly.
for label, url in {"vwce":"https://rebalix.com/en/etf/IE00BK5BQT80",
                   "vfea":"https://rebalix.com/en/etf/IE00BK5BR733"}.items():
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=18) as res:
            body=res.read(900_000).decode("utf-8", errors="replace")
        idx=body.find("Download the published holdings")
        print(json.dumps({"excel_link":label,"context":body[idx-800:idx+220] if idx>=0 else "not found"}))
    except Exception as err:
        print(json.dumps({"excel_link":label,"error":str(err)[:200]}))
