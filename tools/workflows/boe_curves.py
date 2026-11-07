"""Reader for the Bank of England's "latest yield curve data" zip. Standard library only, no financial logic.

The zip holds one .xlsx per curve family. Each workbook's sheet "4. spot curve" has maturities in years on the
row whose first cell is "years:", then one row per business day: an Excel date serial, then continuously
compounded spot yields in percent (the yield curve page says yields are continuously compounded).

Terms (checked 2026-11-07, https://www.bankofengland.co.uk/statistics/yield-curves and /legal): the data are
Bank copyright. The legal page allows download for personal or internal, non-commercial use, and the curve
page has no objection to electronic storage. The OGL applies to the Bank's Database (IADB), and the curve
downloads are not stated to be part of it. The inputs are third-party (Bloomberg, Tradeweb). So the curves
are used locally as a reference, and no value from them is published: reports show only pass or fail.
"""
import datetime as dt
import io
import xml.etree.ElementTree as ET
import zipfile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
URL = "https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip"
FILES = {"ois": "OIS daily data current month.xlsx", "nominal": "GLC Nominal daily data current month.xlsx"}
SHEET = "4. spot curve"
# Deliberately not in tools/recorder/sources.json: the stage D decision (tools/test_tools.py) keeps BoE curve zips out of the
# recorder, as third-party inputs not cleared. Workflow (a) fetches the zip per run and keeps no raw copy.
NOTICE = ("Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), "
          "https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.")


def _sheet_rows(book, sheet_name):
    x = zipfile.ZipFile(io.BytesIO(book))
    shared = []
    if "xl/sharedStrings.xml" in x.namelist():
        for si in ET.fromstring(x.read("xl/sharedStrings.xml")).iter(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(x.read("xl/_rels/workbook.xml.rels"))}
    sheet = next(s for s in ET.fromstring(x.read("xl/workbook.xml")).iter(NS + "sheet") if s.get("name") == sheet_name)
    target = rels[sheet.get(RNS + "id")].lstrip("/")
    path = target if target.startswith("xl/") else "xl/" + target
    for row in ET.fromstring(x.read(path)).iter(NS + "row"):
        cells = []
        for c in row.iter(NS + "c"):
            v = c.find(NS + "v")
            v = v.text if v is not None else ""
            cells.append(shared[int(v)] if c.get("t") == "s" and v else v)
        yield cells


def spot_curves(zip_bytes, family):
    """Returns [(iso date, [(years, zero decimal)])], oldest first; empty maturities are skipped."""
    book = zipfile.ZipFile(io.BytesIO(zip_bytes)).read(FILES[family])
    years, out = None, []
    for cells in _sheet_rows(book, SHEET):
        if not cells:
            continue
        if cells[0] == "years:":
            years = [float(v) if v else None for v in cells[1:]]
            continue
        if years is None:
            continue
        try:
            serial = float(cells[0])
        except ValueError:
            continue
        day = (dt.date(1899, 12, 30) + dt.timedelta(days=int(serial))).isoformat()
        pts = [(t, float(v) / 100) for t, v in zip(years, cells[1:]) if t and v not in ("", None)]
        if pts:
            out.append((day, pts))
    return sorted(out)
