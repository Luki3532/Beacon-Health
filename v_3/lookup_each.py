"""Look up each person on the credentialing list one at a time and write a
separate result file for each.

Search source: the OIG LEIE exclusion database (run v_2/download_leie.py first).

Why this reads the downloaded database instead of the OIG web form:
OIG states on its LEIE instructions page that there are no plans for a public
API, their online search accepts only 5 names at a time, and the verification
step uses a CAPTCHA. Their published guidance is that anyone checking many
names should use the downloadable database. That is what this does. Processing
and output are still strictly one person at a time.

A name match is NOT proof of exclusion. Confirm every hit at
https://exclusions.oig.hhs.gov/ using SSN before any action is taken.

Usage:
    python lookup_each.py
    python lookup_each.py --limit 5     # first 5 people only
"""

import csv
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
ROSTER = HERE.parent / "v_1" / "roster.csv"
LEIE = HERE.parent / "v_2" / "leie.csv"
RESULTS = HERE / "results"
INDEX = HERE / "lookup_index.txt"
VERIFY_URL = "https://exclusions.oig.hhs.gov/"

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


def normalize(text: str) -> str:
    return " ".join(text.strip().upper().split())


def safe_filename(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def pretty_date(raw: str) -> str:
    raw = raw.strip()
    if len(raw) == 8 and raw.isdigit() and raw != "00000000":
        return f"{raw[4:6]}/{raw[6:8]}/{raw[0:4]}"
    return raw or "(none)"


def load_index() -> dict[tuple[str, str], list[dict]]:
    if not LEIE.exists():
        sys.exit(f"LEIE file not found: {LEIE}\nRun v_2/download_leie.py first.")
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with open(LEIE, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            last = normalize(row.get("LASTNAME", ""))
            first = normalize(row.get("FIRSTNAME", ""))
            if last and first:
                index[(last, first)].append(row)
    return index


def search_one(index, last_name: str, first_name: str) -> list[dict]:
    """Search for a single person. Also checks each part of a hyphenated
    surname, as OIG's search tips recommend."""
    first = normalize(first_name)
    surnames = [normalize(last_name)]
    for part in normalize(last_name).replace("-", " ").split():
        if part not in surnames:
            surnames.append(part)

    found: list[dict] = []
    for surname in surnames:
        for record in index.get((surname, first), []):
            if record not in found:
                found.append(record)
    return found


def write_result(person: dict, matches: list[dict], searched: str) -> Path:
    name = f"{person['first_name']} {person['last_name']}"
    path = RESULTS / (
        f"{person['employee_id']}_"
        f"{safe_filename(person['last_name'])}_"
        f"{safe_filename(person['first_name'])}.txt"
    )

    lines = [
        "OIG LEIE EXCLUSION LOOKUP",
        "=" * 60,
        f"Name:        {name}",
        f"Employee ID: {person['employee_id']}",
        f"Manager:     {person['manager']}",
        f"Searched on: {date.today():%m/%d/%Y}",
        f"Source:      OIG LEIE downloadable database",
        f"Name forms searched: {searched}",
        "",
    ]

    if not matches:
        lines += [
            "RESULT: NO MATCH",
            "",
            "This name does not appear in the federal exclusion list.",
        ]
    else:
        lines += [
            f"RESULT: {len(matches)} POSSIBLE NAME MATCH(ES) - REVIEW REQUIRED",
            "",
            "A name match is NOT proof of exclusion. The downloadable database",
            "contains no SSNs, so identity cannot be confirmed from it.",
            f"Verify at {VERIFY_URL} before taking any action.",
            "",
        ]
        for i, record in enumerate(matches, start=1):
            city = normalize(record.get("CITY", ""))
            state = normalize(record.get("STATE", ""))
            code = record.get("EXCLTYPE", "").strip()
            lines += [
                f"--- Record {i} of {len(matches)} ---",
                f"  Name on file:  {normalize(record.get('LASTNAME', ''))}, "
                f"{normalize(record.get('FIRSTNAME', ''))} "
                f"{normalize(record.get('MIDNAME', ''))}".rstrip(),
                f"  Location:      {', '.join(p for p in (city, state) if p) or '(none)'}",
                f"  Specialty:     {normalize(record.get('SPECIALTY', '')) or '(none)'}",
                f"  General:       {normalize(record.get('GENERAL', '')) or '(none)'}",
                f"  NPI on file:   {record.get('NPI', '').strip() or '(none)'}",
                f"  Excluded:      {pretty_date(record.get('EXCLDATE', ''))}",
                f"  Reinstated:    {pretty_date(record.get('REINDATE', ''))}",
                f"  Basis:         {code} - {EXCLUSION_TYPES.get(code, 'see OIG record layout')}",
                "",
            ]

    lines += [
        "-" * 60,
        "Contains real employee data. Keep local; do not share or commit.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    if not ROSTER.exists():
        sys.exit(f"Roster not found: {ROSTER}\nRun v_1/generate_data.py first.")
    with open(ROSTER, newline="", encoding="utf-8") as f:
        roster = list(csv.DictReader(f))
    if limit:
        roster = roster[:limit]

    print(f"Loading LEIE database from {LEIE.name} ...")
    index = load_index()
    print(f"Indexed {len(index):,} distinct excluded individuals.\n")

    RESULTS.mkdir(exist_ok=True)
    summary = []
    started = time.time()

    for position, person in enumerate(roster, start=1):
        name = f"{person['first_name']} {person['last_name']}"
        print(f"[{position}/{len(roster)}] Searching: {name} ... ", end="", flush=True)

        matches = search_one(index, person["last_name"], person["first_name"])
        searched = normalize(person["last_name"])
        if "-" in person["last_name"]:
            searched += " (and each part separately)"

        path = write_result(person, matches, searched)
        status = "NO MATCH" if not matches else f"{len(matches)} MATCH(ES) - REVIEW"
        print(f"{status}  ->  {path.name}")
        summary.append((person, len(matches), path.name))

    elapsed = time.time() - started
    flagged = [s for s in summary if s[1] > 0]

    index_lines = [
        "LEIE LOOKUP INDEX",
        f"Run date:  {date.today():%m/%d/%Y}",
        f"People:    {len(summary)}",
        f"Flagged:   {len(flagged)}",
        f"Elapsed:   {elapsed:.1f}s",
        "",
        "One result file per person in results/:",
        "",
    ]
    for person, count, filename in summary:
        marker = "REVIEW " if count else "clear  "
        index_lines.append(
            f"  {marker} {person['first_name']} {person['last_name']:<22} {filename}"
        )
    INDEX.write_text("\n".join(index_lines), encoding="utf-8")

    print(f"\nWrote {len(summary)} files to {RESULTS}")
    print(f"{len(flagged)} need review. Index: {INDEX.name}")


if __name__ == "__main__":
    main()
