"""Read-only historical spreadsheet/ISIN coverage diagnosis."""
import hashlib
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
BASE = "https://rebalix.com/api/etf/composizione"
IDENTIFIERS = {"VWCE": "IE00BK5BQT80", "VFEA": "IE00BK5BR733"}

def inspect_xlsx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        filenames=z.namelist()
        sheet=next(n for n in filenames if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        strings=[]
        if "xl/sharedStrings.xml" in filenames:
            doc=ET.fromstring(z.read("xl/sharedStrings.xml"))
            strings=["".join(x.itertext()) for x in doc.findall("m:si",NS)]
        rows=[]
        root=ET.fromstring(z.read(sheet))
        for row in root.findall(".//m:sheetData/m:row",NS)[:7]:
            vals=[]
            for cell in row.findall("m:c",NS):
                v=cell.find("m:v",NS)
                inline=cell.find("m:is",NS)
                text=v.text if v is not None else "".join(inline.itertext()) if inline is not None else ""
                if v is not None and cell.get("t")=="s" and text is not None:text=strings[int(text)]
                vals.append([cell.get("r"), (text or "")[:120]])
            rows.append(vals)
        return {"shared_strings_count":len(strings), "worksheet":sheet, "first_rows":rows,
                "worksheet_row_count":len(root.findall(".//m:sheetData/m:row",NS))}

for fund, isin in IDENTIFIERS.items():
    for variant, extra in [("latest", {})]:
        url=BASE+"?"+urlencode({"isin":isin, "lang":"en",**extra})
        try:
            req=Request(url, headers={"User-Agent":"NORTHSTAR Research/1.0"})
            with urlopen(req, timeout=20) as resp:
                data=resp.read(4_000_000)
                meta={"fund":fund, "query":variant, "status":resp.status,
                      "content_type":resp.headers.get("Content-Type"),
                      "content_disposition":resp.headers.get("Content-Disposition"),
                      "bytes":len(data), "sha":hashlib.sha256(data).hexdigest()[:16]}
            if variant=="latest":
                try:meta["excel"]=inspect_xlsx(data)
                except Exception as exc:meta["error_reading_spreadsheet"]=str(exc)[:180]
            print(json.dumps(meta))
        except Exception as exc:
            print(json.dumps({"fund":fund,"query":variant,"error":str(exc)[:250]}))
