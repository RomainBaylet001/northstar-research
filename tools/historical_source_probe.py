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
