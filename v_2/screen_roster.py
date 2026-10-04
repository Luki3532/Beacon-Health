"""Screen the Beacon roster against the OIG LEIE exclusion list.

Reads the roster from v_1/roster.csv and the exclusion database from leie.csv
(run download_leie.py first). Writes a report of every possible name match.

IMPORTANT: a name match is NOT proof of exclusion. The LEIE is matched on name
alone here, and common names produce false positives. OIG requires verification
of any hit through its online search at https://exclusions.oig.hhs.gov/ using
SSN or other identifiers, which the Privacy Act keeps out of the download file.
Every hit this script reports must be confirmed by a person before any action
is taken.

Usage:
    python screen_roster.py
"""

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
ROSTER = HERE.parent / "v_1" / "roster.csv"
LEIE = HERE / "leie.csv"
OUTPUT = HERE / "exclusion_screening.txt"
VERIFY_URL = "https://exclusions.oig.hhs.gov/"

# Exclusion type codes seen in the file are documented in OIG's record layout.
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


def read_roster() -> list[dict]:
    if not ROSTER.exists():
        sys.exit(f"Roster not found: {ROSTER}\nRun v_1/generate_data.py first.")
    with open(ROSTER, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def index_leie() -> dict[tuple[str, str], list[dict]]:
    """Map (LASTNAME, FIRSTNAME) -> excluded individual records."""
    if not LEIE.exists():
        sys.exit(f"LEIE file not found: {LEIE}\nRun download_leie.py first.")
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with open(LEIE, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            last = normalize(row.get("LASTNAME", ""))
            first = normalize(row.get("FIRSTNAME", ""))
            if last and first:  # individuals only; businesses have BUSNAME instead
                index[(last, first)].append(row)
    return index


def describe(record: dict) -> list[str]:
    code = record.get("EXCLTYPE", "").strip()
    excl_date = record.get("EXCLDATE", "").strip()
    pretty_date = (
        f"{excl_date[4:6]}/{excl_date[6:8]}/{excl_date[0:4]}"
        if len(excl_date) == 8 and excl_date.isdigit()
        else excl_date or "unknown"
    )
    middle = normalize(record.get("MIDNAME", ""))
    city = normalize(record.get("CITY", ""))
    state = normalize(record.get("STATE", ""))
    location = ", ".join(p for p in (city, state) if p) or "no location on file"
    return [
        f"      middle name on file: {middle or '(none)'}",
        f"      location:            {location}",
        f"      specialty:           {normalize(record.get('SPECIALTY', '')) or '(none)'}",
        f"      excluded:            {pretty_date}",
        f"      basis:               {code} - {EXCLUSION_TYPES.get(code, 'see OIG record layout')}",
    ]


def main() -> None:
    roster = read_roster()
    leie = index_leie()

    hits = []
    for person in roster:
        key = (normalize(person["last_name"]), normalize(person["first_name"]))
        matches = leie.get(key)
        if matches:
            hits.append((person, matches))

    lines = [
        "OIG LEIE EXCLUSION SCREENING",
        f"Run date:        {date.today():%m/%d/%Y}",
        f"Roster:          {len(roster)} people",
        f"LEIE individuals:{len(leie):,} distinct names",
        "",
        "Matching is on first and last name only. A match is NOT proof of",
        f"exclusion. Confirm every hit at {VERIFY_URL}",
        "before taking any action.",
        "",
        "=" * 70,
        "",
    ]

    if not hits:
        lines.append("RESULT: no roster names matched the LEIE.")
        lines.append("")
        lines.append("No one on the roster appears on the federal exclusion list by name.")
    else:
        lines.append(f"RESULT: {len(hits)} roster name(s) need human review.")
        lines.append("")
        for person, matches in hits:
            name = f"{person['first_name']} {person['last_name']}"
            lines.append(f"  {name} ({person['employee_id']}) - manager {person['manager']}")
            lines.append(f"    {len(matches)} LEIE record(s) with this first and last name:")
            for i, record in enumerate(matches, start=1):
                lines.append(f"    record {i}:")
                lines.extend(describe(record))
            lines.append(f"    ACTION: confirm at {VERIFY_URL} before acting.")
            lines.append("")

    text = "\n".join(lines)
    OUTPUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
