"""
v_9 - Indiana Medicaid provider sanctions screening (import-based).

WHY IMPORT INSTEAD OF DOWNLOAD
------------------------------
Beacon's home base is South Bend, Indiana, and the roster works the MI/IN
border, so Indiana sanctions are a real blind spot that OIG + Michigan miss.
But unlike OIG LEIE and Michigan MDHHS, Indiana does NOT publish a single clean
machine-readable file at a stable URL. The "Termination for Cause and Provider
Sanctions" information is posted on a state web page, and the list itself is
distributed as a document rather than a data feed:

    https://www.in.gov/medicaid/providers/provider-references/termination-for-cause-and-provider-sanctions/

So the honest, reliable path is an IMPORT: a person downloads the current list
from that page, saves it here, and this screens the roster against it. That is
exactly the "Import file" path the console advertises for this source. No
scraping, no guessing a URL that may change.

WHAT TO DROP IN
---------------
Save the Indiana sanctions list in this folder as one of:

    in_sanctions.csv      (columns including a name field; auto-detected)
    in_sanctions.xlsx     (first sheet; parsed with v_4's stdlib reader)

Then run this script. A name match is a LEAD, not proof - Indiana's list, like
the others, has no SSN. Confirm identity (v_7 NPPES) and the record before any
action.

Usage:
    python screen_indiana.py
    python screen_indiana.py --make-sample   # write a tiny demo file to test the flow
"""

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EMPLOYEE_DATA = ROOT / "v_1" / "employee_data.csv"

CSV_IN = HERE / "in_sanctions.csv"
XLSX_IN = HERE / "in_sanctions.xlsx"
OUTPUT = HERE / "output"
SUMMARY_FILE = OUTPUT / "FINDINGS_SUMMARY.txt"

SOURCE_URL = ("https://www.in.gov/medicaid/providers/provider-references/"
              "termination-for-cause-and-provider-sanctions/")

# Column headers that might hold a person's name, in rough priority order.
NAME_HINTS = ("provider name", "name", "last name", "individual", "excluded")


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
        sys.path.insert(0, str(ROOT / "v_4"))
        try:
            import xlsx_reader  # reuse the stdlib .xlsx parser from v_4
        except ImportError as exc:
            raise SystemExit("Could not load v_4/xlsx_reader.py: {}".format(exc))
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
    low = {h.lower(): h for h in headers}
    for hint in NAME_HINTS:
        for key, original in low.items():
            if hint in key:
                return original
    return headers[0]


def tokens(value):
    return {t for t in (value or "").upper().replace(",", " ").split() if len(t) > 1}


def screen():
    rows, label = load_imported_rows()
    people = read_csv(EMPLOYEE_DATA)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    if rows is None:
        SUMMARY_FILE.write_text("\n".join([
            "INDIANA MEDICAID SANCTIONS - NOT YET IMPORTED",
            "=" * 60,
            "Generated: {}".format(date.today().isoformat()),
            "",
            "No Indiana sanctions file is present. To connect this source:",
            "  1. Open " + SOURCE_URL,
            "  2. Download the current sanctions / termination list",
            "  3. Save it here as in_sanctions.csv or in_sanctions.xlsx",
            "  4. Run:  python screen_indiana.py",
            "",
            "To preview the flow with fake data:",
            "     python screen_indiana.py --make-sample",
        ]), encoding="utf-8")
        print("No Indiana file imported yet. See", SUMMARY_FILE)
        print("Tip: 'python screen_indiana.py --make-sample' to test the flow.")
        return

    name_col = pick_name_column(rows)
    index = defaultdict(list)
    for rec in rows:
        for tok in tokens(rec.get(name_col, "")):
            index[tok].append(rec)

    flagged = []
    for person in people:
        last = person["last_name"].strip().upper()
        first = person["first_name"].strip().upper()
        candidates = index.get(last, [])
        hits = [r for r in candidates
                if first in tokens(r.get(name_col, ""))] or candidates
        if hits:
            flagged.append((person, hits[:3]))

    lines = [
        "INDIANA MEDICAID PROVIDER SANCTIONS - SCREENING SUMMARY",
        "=" * 60,
        "Generated: {}".format(date.today().isoformat()),
        "Source:    {}".format(SOURCE_URL),
        "Imported:  {}  ({} rows, name column '{}')".format(
            label, len(rows), name_col),
        "People:    {}".format(len(people)),
        "Flagged:   {}".format(len(flagged)),
        "",
        "A name match is a LEAD, not proof. Indiana's list carries no SSN;",
        "confirm identity (v_7 NPPES) and the record before any action.",
        "",
    ]
    for person, hits in flagged:
        lines.append("  {} {} {}  -> {} Indiana record(s)".format(
            person["employee_id"], person["first_name"],
            person["last_name"], len(hits)))
    if not flagged:
        lines.append("  No name matches against the imported Indiana list.")
    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("Screened {} people against {} Indiana rows: {} flagged.".format(
        len(people), len(rows), len(flagged)))
    print("  Output:", SUMMARY_FILE)


def make_sample():
    """Write a tiny demo file so the import->screen flow can be tested."""
    people = read_csv(EMPLOYEE_DATA)
    sample_names = []
    if people:
        # Include one real roster name so a match is demonstrable, plus noise.
        p = people[0]
        sample_names.append("{}, {}".format(p["last_name"], p["first_name"]))
    sample_names += ["DOE, JOHN", "PUBLIC, JANE Q"]
    with open(CSV_IN, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Provider Name", "Sanction Type", "Effective Date"])
        for name in sample_names:
            writer.writerow([name, "DEMO - not a real sanction", "01/2026"])
    print("Wrote demo file:", CSV_IN)
    print("This is DEMO DATA. Now run: python screen_indiana.py")


def main():
    if "--make-sample" in sys.argv[1:]:
        make_sample()
        return
    screen()


if __name__ == "__main__":
    main()
