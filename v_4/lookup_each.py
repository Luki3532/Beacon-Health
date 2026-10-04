"""Look up each person on the credentialing list one at a time against TWO
exclusion databases and write a separate result file for each person.

Sources searched
----------------
1. OIG LEIE (federal)
   Downloadable database from v_2/download_leie.py.
   OIG states there are no plans for a public API and directs anyone checking
   many names to the downloadable file.

2. Michigan Medicaid Sanctioned Provider List (state)
   Published by MDHHS as an .xlsx file. No API exists.
   MDHHS's own guidance is that the federal lists should be monitored
   alongside theirs, which is exactly what this script does.

Why both: MDHHS notes that providers sanctioned by the state may not appear
federally, and that some providers serving Medicaid beneficiaries are not
enrolled with MDHHS at all. Neither list is complete on its own.

A name match is NOT proof of exclusion. Neither public file contains SSNs, so
identity cannot be confirmed from them. Verify every hit with the issuing
agency before any action is taken.

Usage:
    python lookup_each.py
    python lookup_each.py --limit 5     # first 5 people only
"""

import csv
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from xlsx_reader import read_rows

HERE = Path(__file__).resolve().parent
ROSTER = HERE.parent / "v_1" / "roster.csv"
LEIE = HERE.parent / "v_2" / "leie.csv"
MI_XLSX = HERE / "mi_sanctions.xlsx"
RESULTS = HERE / "results"
INDEX = HERE / "lookup_index.txt"

LEIE_VERIFY_URL = "https://exclusions.oig.hhs.gov/"
MI_CONTACT = "MDHHS-SanctionProviderList@michigan.gov"

EXCLUSION_TYPES = {
    "1128a1": "Conviction of program-related crimes",
    "1128a2": "Conviction relating to patient abuse or neglect",
    "1128a3": "Felony conviction relating to health care fraud",
    "1128a4": "Felony conviction relating to controlled substances",
    "1128b1": "Misdemeanor conviction relating to health care fraud",
    "1128b2": "Conviction relating to obstruction of an investigation",
    "1128b3": "Misdemeanor conviction relating to controlled substances",
    "1128b4": "License revocation, suspension, or surrender",
    "1128b5": "Exclusion or suspension under a federal or state program",
    "1128b6": "Claims for excessive charges or unnecessary services",
    "1128b7": "Fraud, kickbacks, and other prohibited activities",
    "1128b8": "Entities controlled by a sanctioned individual",
    "1128b14": "Default on health education loan or scholarship obligations",
}

# Excel stores dates as a day count from this epoch.
EXCEL_EPOCH = datetime(1899, 12, 30)


def normalize(text):
    return " ".join((text or "").strip().upper().split())


def safe_filename(text):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def blank_if_zeros(raw):
    """LEIE pads empty fields with zeros rather than leaving them blank."""
    raw = (raw or "").strip()
    return "" if raw.strip("0") == "" else raw


def pretty_leie_date(raw):
    """LEIE dates arrive as YYYYMMDD."""
    raw = blank_if_zeros(raw)
    if len(raw) == 8 and raw.isdigit():
        return "{}/{}/{}".format(raw[4:6], raw[6:8], raw[0:4])
    return raw or "(none)"


def pretty_excel_date(raw):
    """MDHHS dates arrive as Excel day-count serial numbers."""
    raw = (raw or "").strip()
    if not raw:
        return "(none)"
    try:
        serial = float(raw)
    except ValueError:
        return raw
    if serial <= 0:
        return "(none)"
    return (EXCEL_EPOCH + timedelta(days=serial)).strftime("%m/%d/%Y")


def surname_forms(last_name):
    """OIG's search tips recommend trying each part of a hyphenated surname."""
    forms = [normalize(last_name)]
    for part in normalize(last_name).replace("-", " ").split():
        if part not in forms:
            forms.append(part)
    return forms


def load_leie_index():
    if not LEIE.exists():
        sys.exit("LEIE file not found: {}\nRun v_2/download_leie.py first.".format(LEIE))

    index = defaultdict(list)
    with open(LEIE, newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            last = normalize(row.get("LASTNAME", ""))
            first = normalize(row.get("FIRSTNAME", ""))
            if last and first:
                index[(last, first)].append(row)
    return index


def load_mi_index():
    """Index the MDHHS spreadsheet by (last, first).

    Only rows with an individual's name are indexed. Rows that carry just an
    entity name are organizations, not people on our roster.
    """
    if not MI_XLSX.exists():
        sys.exit(
            "Michigan sanctions file not found: {}\n"
            "Run v_4/download_mi_sanctions.py first.".format(MI_XLSX)
        )

    rows = list(read_rows(MI_XLSX))

    # The first row is a title block; the header is the row containing
    # "Last Name". Find it rather than assuming a fixed position.
    header_at = None
    for position, row in enumerate(rows):
        if any(normalize(cell) == "LAST NAME" for cell in row):
            header_at = position
            break
    if header_at is None:
        sys.exit("Could not find the header row in the MDHHS spreadsheet.")

    headers = [normalize(cell) for cell in rows[header_at]]

    # "Sanction Source" appears twice. Make the duplicate unique.
    seen = {}
    for position, name in enumerate(headers):
        if name in seen:
            seen[name] += 1
            headers[position] = "{} {}".format(name, seen[name] + 1)
        else:
            seen[name] = 0

    index = defaultdict(list)
    total = 0
    for row in rows[header_at + 1:]:
        record = {}
        for position, name in enumerate(headers):
            record[name] = row[position] if position < len(row) else ""

        last = normalize(record.get("LAST NAME", ""))
        first = normalize(record.get("FIRST NAME", ""))
        if not last or not first:
            continue

        total += 1
        index[(last, first)].append(record)

    return index, total


def search_index(index, last_name, first_name):
    first = normalize(first_name)
    found = []
    for surname in surname_forms(last_name):
        for record in index.get((surname, first), []):
            if record not in found:
                found.append(record)
    return found


def format_leie_section(matches):
    if not matches:
        return [
            "RESULT: NO MATCH",
            "",
            "This name does not appear in the federal exclusion list.",
        ]

    lines = [
        "RESULT: {} POSSIBLE NAME MATCH(ES) - REVIEW REQUIRED".format(len(matches)),
        "",
        "A name match is NOT proof of exclusion. The downloadable database",
        "contains no SSNs, so identity cannot be confirmed from it.",
        "Verify at {} before taking any action.".format(LEIE_VERIFY_URL),
        "",
    ]
    for position, record in enumerate(matches, start=1):
        city = normalize(record.get("CITY", ""))
        state = normalize(record.get("STATE", ""))
        code = (record.get("EXCLTYPE") or "").strip()
        name_on_file = "{}, {} {}".format(
            normalize(record.get("LASTNAME", "")),
            normalize(record.get("FIRSTNAME", "")),
            normalize(record.get("MIDNAME", "")),
        ).rstrip()
        lines += [
            "--- Record {} of {} ---".format(position, len(matches)),
            "  Name on file:  {}".format(name_on_file),
            "  Location:      {}".format(", ".join(p for p in (city, state) if p) or "(none)"),
            "  Specialty:     {}".format(normalize(record.get("SPECIALTY", "")) or "(none)"),
            "  General:       {}".format(normalize(record.get("GENERAL", "")) or "(none)"),
            "  NPI on file:   {}".format(blank_if_zeros(record.get("NPI")) or "(none)"),
            "  Excluded:      {}".format(pretty_leie_date(record.get("EXCLDATE", ""))),
            "  Reinstated:    {}".format(pretty_leie_date(record.get("REINDATE", ""))),
            "  Basis:         {} - {}".format(
                code or "(none)", EXCLUSION_TYPES.get(code, "see OIG record layout")
            ),
            "",
        ]
    return lines


def format_mi_section(matches):
    if not matches:
        return [
            "RESULT: NO MATCH",
            "",
            "This name does not appear on the Michigan sanctioned provider list.",
        ]

    lines = [
        "RESULT: {} POSSIBLE NAME MATCH(ES) - REVIEW REQUIRED".format(len(matches)),
        "",
        "A name match is NOT proof of sanction. Confirm with MDHHS at",
        "{} before taking any action.".format(MI_CONTACT),
        "",
    ]
    for position, record in enumerate(matches, start=1):
        name_on_file = "{}, {} {}".format(
            normalize(record.get("LAST NAME", "")),
            normalize(record.get("FIRST NAME", "")),
            normalize(record.get("MIDDLE NAME", "")),
        ).rstrip()
        sources = [record.get("SANCTION SOURCE", ""), record.get("SANCTION SOURCE 2", "")]
        sources = [s.strip() for s in sources if s and s.strip()]
        lines += [
            "--- Record {} of {} ---".format(position, len(matches)),
            "  Name on file:  {}".format(name_on_file),
            "  Entity:        {}".format(record.get("ENTITY NAME", "") or "(none)"),
            "  Category:      {}".format(record.get("PROVIDER CATEGORY", "") or "(none)"),
            "  City:          {}".format(record.get("CITY", "") or "(none)"),
            "  NPI on file:   {}".format(record.get("NPI#", "") or "(none)"),
            "  License #:     {}".format(record.get("LICENSE#", "") or "(none)"),
            "  Sanction date: {}".format(pretty_excel_date(record.get("SANCTION DATE1", ""))),
            "  Second date:   {}".format(pretty_excel_date(record.get("SANCTION DATE2", ""))),
            "  Source:        {}".format(", ".join(sources) or "(none)"),
            "  Reason:        {}".format(record.get("REASON", "") or "(none)"),
            "",
        ]
    return lines


def write_result(person, leie_matches, mi_matches, searched):
    name = "{} {}".format(person["first_name"], person["last_name"])
    path = RESULTS / "{}_{}_{}.txt".format(
        person["employee_id"],
        safe_filename(person["last_name"]),
        safe_filename(person["first_name"]),
    )

    total = len(leie_matches) + len(mi_matches)
    overall = "REVIEW REQUIRED" if total else "CLEAR"

    lines = [
        "EXCLUSION / SANCTION LOOKUP",
        "=" * 64,
        "Name:        {}".format(name),
        "Employee ID: {}".format(person["employee_id"]),
        "Manager:     {}".format(person["manager"]),
        "Searched on: {:%m/%d/%Y}".format(date.today()),
        "Name forms searched: {}".format(searched),
        "",
        "OVERALL: {}  (federal: {}, state: {})".format(
            overall, len(leie_matches), len(mi_matches)
        ),
        "",
        "-" * 64,
        "SOURCE 1 OF 2: OIG LEIE (federal exclusion list)",
        "-" * 64,
    ]
    lines += format_leie_section(leie_matches)
    lines += [
        "",
        "-" * 64,
        "SOURCE 2 OF 2: Michigan Medicaid Sanctioned Provider List (MDHHS)",
        "-" * 64,
    ]
    lines += format_mi_section(mi_matches)
    lines += [
        "",
        "-" * 64,
        "Neither public file contains SSNs. A name match alone never confirms",
        "identity. Contains real employee data - keep local, do not share or commit.",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    if not ROSTER.exists():
        sys.exit("Roster not found: {}\nRun v_1/generate_data.py first.".format(ROSTER))

    with open(ROSTER, newline="", encoding="utf-8") as handle:
        roster = list(csv.DictReader(handle))
    if limit:
        roster = roster[:limit]

    print("Loading federal LEIE database from {} ...".format(LEIE.name))
    leie_index = load_leie_index()
    print("  Indexed {:,} distinct excluded individuals.".format(len(leie_index)))

    print("Loading Michigan sanctioned provider list from {} ...".format(MI_XLSX.name))
    mi_index, mi_total = load_mi_index()
    print("  Indexed {:,} sanctioned individuals ({:,} distinct names).\n".format(
        mi_total, len(mi_index)
    ))

    RESULTS.mkdir(exist_ok=True)
    summary = []
    started = time.time()

    for position, person in enumerate(roster, start=1):
        name = "{} {}".format(person["first_name"], person["last_name"])
        print("[{}/{}] Searching: {} ... ".format(position, len(roster), name),
              end="", flush=True)

        leie_matches = search_index(leie_index, person["last_name"], person["first_name"])
        mi_matches = search_index(mi_index, person["last_name"], person["first_name"])

        searched = normalize(person["last_name"])
        if "-" in person["last_name"]:
            searched += " (and each part separately)"

        path = write_result(person, leie_matches, mi_matches, searched)

        total = len(leie_matches) + len(mi_matches)
        if total:
            status = "REVIEW - federal {}, state {}".format(len(leie_matches), len(mi_matches))
        else:
            status = "CLEAR"
        print("{}  ->  {}".format(status, path.name))

        summary.append((person, len(leie_matches), len(mi_matches), path.name))

    elapsed = time.time() - started
    flagged = [item for item in summary if item[1] or item[2]]

    index_lines = [
        "EXCLUSION / SANCTION LOOKUP INDEX",
        "Run date:  {:%m/%d/%Y}".format(date.today()),
        "People:    {}".format(len(summary)),
        "Flagged:   {}".format(len(flagged)),
        "Sources:   OIG LEIE (federal) + MDHHS Sanctioned Provider List (Michigan)",
        "Elapsed:   {:.1f}s".format(elapsed),
        "=" * 64,
        "",
    ]
    for person, leie_count, mi_count, filename in summary:
        marker = "REVIEW" if (leie_count or mi_count) else "clear "
        index_lines.append(
            "{}  {:<6}  {:<28}  fed:{}  mi:{}  {}".format(
                marker,
                person["employee_id"],
                "{} {}".format(person["first_name"], person["last_name"]),
                leie_count,
                mi_count,
                filename,
            )
        )
    INDEX.write_text("\n".join(index_lines), encoding="utf-8")

    print("\nDone in {:.1f}s.".format(elapsed))
    print("Wrote {} result files to {}".format(len(summary), RESULTS))
    print("Index: {}".format(INDEX))
    print("Flagged for review: {}".format(len(flagged)))


if __name__ == "__main__":
    main()
