"""
v_10 - ARRT disciplinary sanctions screening (import-based).

FAST PATH: --fetch
------------------
One HTTP request for the whole public list (not one search per employee), then
the roster is matched locally. The full list is NOT saved to disk: only the
matches are written to the summary. If the page does not return every row
(e.g. rows are paged server-side or loaded by script), the run stops instead of
screening a partial list, because a partial list would give false "clear"
results. If that happens, find the JSON request the page makes (browser
DevTools > Network) and pass it with --url.

ARRT's Terms of Use limit copying site content to personal, noncommercial use
without written permission. Beacon's use is an employer compliance screen, so
confirm with ARRT (651.687.0048) that automated retrieval is acceptable. The
list page is allowed by robots.txt; there is no CAPTCHA.

FILE IMPORT (alternative)
-------------------------
Save an export as arrt_sanctions.csv / arrt_sanctions.xlsx in this folder and
run without --fetch.

WHAT TO DROP IN
---------------
Save the ARRT sanctioned list export in this folder as one of:

    arrt_sanctions.csv
    arrt_sanctions.xlsx

Then run this script. A name match is a LEAD, not proof.
Only public reprimands are published by ARRT; private reprimands are not.

Usage:
    python screen_arrt_sanctions.py --fetch
    python screen_arrt_sanctions.py --fetch --url <json-or-html-url>
    python screen_arrt_sanctions.py            # screen a saved export file

No sample or demo data is ever generated. For one-off manual lookups use
record_arrt_sanctions_check.py.
"""

import csv
import importlib.util
import json
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EMPLOYEE_DATA = ROOT / "v_1" / "employee_data.csv"

CSV_IN = HERE / "arrt_sanctions.csv"
XLSX_IN = HERE / "arrt_sanctions.xlsx"
OUTPUT = HERE / "output"
SUMMARY_FILE = OUTPUT / "FINDINGS_SUMMARY.txt"
WEB_SYNC_FILE = OUTPUT / "web_sync.json"

SOURCE_URL = "https://www.arrt.org/sanctioned-list"
LIST_URL = "https://www.arrt.org/SanctionList/GetSanctionList"
USER_AGENT = "BeaconCredentialTracker/1.0 (employer compliance screening; one request)"

# Column headers that may contain person names in exported reports.
NAME_HINTS = (
    "name",
    "individual",
    "first name",
    "last name",
    "registrant",
)


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_imported_rows():
    """Return (rows, source_label). Prefer CSV; fall back to XLSX via v_4."""
    if CSV_IN.exists():
        return read_csv(CSV_IN), CSV_IN.name
    if XLSX_IN.exists():
        module_path = ROOT / "v_4" / "xlsx_reader.py"
        spec = importlib.util.spec_from_file_location("v4_xlsx_reader", module_path)
        if spec is None or spec.loader is None:
            raise SystemExit("Could not load v_4/xlsx_reader.py")
        xlsx_reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(xlsx_reader)

        table = list(xlsx_reader.read_rows(XLSX_IN))
        if not table:
            return [], XLSX_IN.name
        header = [h.strip() for h in table[0]]
        rows = [dict(zip(header, row)) for row in table[1:]]
        return rows, XLSX_IN.name
    return None, None


def pick_name_column(rows):
    if not rows:
        return None
    headers = list(rows[0].keys())
    lower = {h.lower(): h for h in headers}
    for hint in NAME_HINTS:
        for key, original in lower.items():
            if hint in key:
                return original
    return headers[0]


class _TableParser(HTMLParser):
    """Collect every <tr> as a list of cell texts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None


def fetch_rows(url):
    """One GET. Returns (rows, total_rows_the_page_claims_or_None)."""
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
        content_type = response.headers.get("Content-Type", "")

    if "json" in content_type or body.lstrip().startswith(("[", "{")):
        data = json.loads(body)
        total = None
        if isinstance(data, dict):
            total = data.get("recordsTotal", data.get("total"))
            lists = [value for value in data.values() if isinstance(value, list)]
            if len(lists) != 1:
                raise ValueError("ARRT JSON must contain exactly one list of records.")
            data = lists[0]
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError("ARRT JSON contains invalid sanction records.")
        rows = [{str(k): "" if v is None else str(v) for k, v in item.items()}
                for item in data]
        if total is not None and (not isinstance(total, int) or isinstance(total, bool)):
            raise ValueError("ARRT JSON has an invalid total record count.")
        return rows, total if total is not None else len(rows)

    parser = _TableParser()
    parser.feed(body)
    header_at = next(
        (i for i, row in enumerate(parser.rows)
         if any(c.lower() == "name" for c in row)
         and any("arrt id" in c.lower() for c in row)),
        None,
    )
    if header_at is None:
        return [], None
    if "</table>" not in body.lower() or parser._row is not None or parser._cell is not None:
        raise ValueError("Incomplete ARRT table: the response ended before the table closed.")
    header = parser.rows[header_at]
    rows = []
    for cells in parser.rows[header_at + 1:]:
        if len(cells) == len(header):
            rows.append({h: c for h, c in zip(header, cells) if h})
    if any(len(cells) != len(header) for cells in parser.rows[header_at + 1:]):
        raise ValueError("Incomplete ARRT table: a row has missing or extra columns.")
    if any(not row.get("Name") or not row.get("ARRT ID") for row in rows):
        raise ValueError("Invalid ARRT table: a row is missing its name or ARRT ID.")
    claimed = re.search(r"of\s+([\d,]+)\s+items", re.sub(r"<[^>]+>", " ", body))
    total = int(claimed.group(1).replace(",", "")) if claimed else None
    return rows, total


def norm(value):
    """Upper-case, drop apostrophes/periods, collapse whitespace."""
    out = []
    for ch in (value or "").upper():
        if ch in "'.\u2019":
            continue
        out.append(ch if ch.isalnum() or ch in " -" else " ")
    return " ".join("".join(out).split())


def split_name(value):
    """'Last, First Middle' -> ('LAST', ['FIRST', 'MIDDLE']). No comma: last word is the surname."""
    if "," in (value or ""):
        last, first = value.split(",", 1)
        return norm(last), norm(first).split()
    words = norm(value).split()
    return (words[-1], words[:-1]) if words else ("", [])


def screen(fetch=False, url=None):
    if fetch:
        url = url or LIST_URL
        rows, claimed = fetch_rows(url)
        if not rows:
            raise SystemExit(
                "No sanction rows found at {}.\nThe table is probably loaded by "
                "script. In a browser open the page, DevTools > Network, find the "
                "request that returns the list, and run again with --url <that url>."
                .format(url))
        if claimed is not None and len(rows) != claimed:
            raise SystemExit(
                "Got {} of {} rows. Screening a partial list would give false "
                "'clear' results, so nothing was written.\nThe list is likely paged "
                "server-side; find the full-list request and pass it with --url."
                .format(len(rows), claimed))
        label = "{} (fetched {})".format(url, date.today().isoformat())
    else:
        rows, label = load_imported_rows()
    people = read_csv(EMPLOYEE_DATA)
    if fetch and not people:
        raise ValueError("No employee roster is available for ARRT screening.")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    if rows is None:
        if WEB_SYNC_FILE.exists():
            WEB_SYNC_FILE.unlink()
        SUMMARY_FILE.write_text("\n".join([
            "ARRT DISCIPLINARY SANCTIONS - NOT YET IMPORTED",
            "=" * 60,
            "Generated: {}".format(date.today().isoformat()),
            "",
            "No ARRT sanctions file is present. To connect this source:",
            "  Fetch directly:  python v_10/screen_arrt_sanctions.py --fetch",
            "  Or import a file:",
            "  1. Open " + SOURCE_URL,
            "  2. Export or save results as CSV/XLSX",
            "  3. Save here as arrt_sanctions.csv or arrt_sanctions.xlsx",
            "  4. Run: python v_10/screen_arrt_sanctions.py",
            "",
            "Compliance note:",
            "  - ARRT Terms of Use limit copying to personal, noncommercial use",
            "    without written permission; confirm with ARRT (651.687.0048).",
            "  - ARRT publishes public reprimands; private reprimands are not published.",
            "",
            "No export? Record manual lookups instead:",
            "     python v_10/record_arrt_sanctions_check.py --pending",
        ]), encoding="utf-8")
        print("No ARRT sanctions file imported yet. See", SUMMARY_FILE)
        print("Tip: record manual lookups with v_10/record_arrt_sanctions_check.py")
        return

    name_col = pick_name_column(rows)
    index = defaultdict(list)
    for rec in rows:
        rec_last, rec_first = split_name(rec.get(name_col, ""))
        if rec_last:
            index[rec_last].append((rec, rec_first))

    # Match on the WHOLE last name (so 'Vander Stel' works) AND the first word
    # of the first name, so a shared surname alone does not flag someone.
    flagged = []
    for person in people:
        last = norm(person["last_name"])
        first_words = norm(person["first_name"]).split()
        first = first_words[0] if first_words else ""
        hits = [rec for rec, rec_first in index.get(last, [])
                if first and first in rec_first]
        if hits:
            flagged.append((person, hits))

    lines = [
        "ARRT DISCIPLINARY SANCTIONS - SCREENING SUMMARY",
        "=" * 60,
        "Generated: {}".format(date.today().isoformat()),
        "Source:    {}".format(SOURCE_URL),
        "Imported:  {}  ({} rows, name column '{}')".format(label, len(rows), name_col),
        "People:    {}".format(len(people)),
        "Flagged:   {}".format(len(flagged)),
        "",
        "A name match is a LEAD, not proof.",
        "ARRT publishes public reprimands; private reprimands are not published.",
        "Read ARRT Terms of Use before any website automation.",
        "",
    ]

    if flagged:
        lines.append("FLAGGED FOR REVIEW")
        lines.append("=" * 60)
    for person, hits in flagged:
        # Format parsed by presentation/prod v2/build_data.py - keep in sync.
        lines.append("  {}  {} {}   arrt:{}".format(
            person["employee_id"], person["first_name"], person["last_name"], len(hits)
        ))
        for rec in hits:
            detail = " | ".join(
                str(v).strip() for v in rec.values() if v is not None and str(v).strip()
            )
            lines.append("      > {}".format(detail))

    if not flagged:
        lines.append("  No name matches against the imported ARRT sanctions list.")

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")
    if fetch:
        WEB_SYNC_FILE.write_text(json.dumps({
            "source": url,
            "updatedOn": date.today().isoformat(),
            "records": len(rows),
            "people": len(people),
            "flagged": len(flagged),
        }, indent=2), encoding="utf-8")
    elif WEB_SYNC_FILE.exists():
        WEB_SYNC_FILE.unlink()
    print("Screened {} people against {} ARRT rows: {} flagged.".format(
        len(people), len(rows), len(flagged)
    ))
    print("  Output:", SUMMARY_FILE)


def main():
    argv = sys.argv[1:]
    url = argv[argv.index("--url") + 1] if "--url" in argv else None
    screen(fetch="--fetch" in argv, url=url)


if __name__ == "__main__":
    main()
