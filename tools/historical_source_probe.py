"""Targeted read-only discovery of public historical Vanguard holdings downloads."""
import json
import re
from urllib.request import Request, urlopen

for label, url in {
    "vwce": "https://rebalix.com/en/etf/IE00BK5BQT80",
    "vfea": "https://rebalix.com/en/etf/IE00BK5BR733",
}.items():
    try:
        req = Request(url, headers={"User-Agent": "NORTHSTAR Research/1.0"})
        with urlopen(req, timeout=15) as response:
            html = response.read(900_000).decode("utf-8", errors="replace")
        match = re.search(r"Download the published holdings", html)
        before = html[max(0, match.start() - 750):match.end() + 160] if match else "NOT FOUND"
        print(json.dumps({"fund": label, "download_anchor": before}))
    except Exception as exc:
        print(json.dumps({"fund": label, "error": str(exc)}))
