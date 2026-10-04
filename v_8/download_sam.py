"""
v_8 - SAM.gov exclusions screening (federal debarments).

WHAT THIS ADDS OVER OIG LEIE
----------------------------
OIG LEIE (v_2) covers healthcare-program exclusions. SAM.gov covers the broader
federal picture: debarments and exclusions across ALL federal programs, from
every agency, consolidated by the GSA. Someone can be barred government-wide
without yet appearing on the OIG list, so SAM is a genuine second net, not a
duplicate.

WHY THIS ONE NEEDS A KEY (AND ARRT DOES NOT GET ONE)
----------------------------------------------------
SAM.gov publishes a real, sanctioned, programmatic path - but it is gated by a
free API key, not wide open like LEIE. That is the opposite of ARRT: ARRT has
no public programmatic access at all and forbids scraping. SAM invites
automated use, it just wants you registered. So this is buildable and correct;
it simply cannot run until a key is in place.

HOW TO GET A KEY (free, a few minutes)
--------------------------------------
  1. Create / sign in at https://sam.gov
  2. Account Details -> request a public API key
  3. Put it in an environment variable before running:
         setx SAM_API_KEY "your-key-here"      (Windows, new shell after)
     or pass --api-key on the command line.

Docs: https://open.gsa.gov/api/exclusions-api/

Usage:
    python download_sam.py                 # uses SAM_API_KEY from environment
    python download_sam.py --api-key KEY   # or pass it directly
    python download_sam.py --screen        # after download, screen the roster
"""

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EMPLOYEE_DATA = ROOT / "v_1" / "employee_data.csv"

OUTPUT = HERE / "output"
RAW = HERE / "sam_exclusions.json"
SUMMARY_FILE = OUTPUT / "FINDINGS_SUMMARY.txt"

# Public Exclusions API (v4). Returns JSON pages of exclusion records.
API = "https://api.sam.gov/entity-information/v4/exclusions"
PAGE_SIZE = 100
TIMEOUT = 60


class SamKeyMissing(RuntimeError):
    """Raised when no API key is configured. Message explains how to fix it."""


def get_api_key(argv):
    if "--api-key" in argv:
        return argv[argv.index("--api-key") + 1]
    key = os.environ.get("SAM_API_KEY", "").strip()
    if not key:
        raise SamKeyMissing(
            "No SAM.gov API key found.\n"
            "  - Get a free key at https://sam.gov (Account Details -> API Key)\n"
            "  - Then: setx SAM_API_KEY \"your-key\"  and open a new shell,\n"
            "    or run:  python download_sam.py --api-key YOUR_KEY\n"
            "  - API docs: https://open.gsa.gov/api/exclusions-api/"
        )
    return key


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fetch_all(api_key):
    """Page through the exclusions API and return a flat list of records."""
    records = []
    offset = 0
    while True:
        params = {
            "api_key": api_key,
            "classification": "Individual",
            "isActive": "Y",
            "size": PAGE_SIZE,
            "offset": offset,
        }
        url = API + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, headers={"User-Agent": "Beacon-credential-tracker/1.0"}
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https host
            page = json.loads(response.read().decode("utf-8"))

        batch = page.get("excludedEntity", []) or page.get("results", []) or []
        records.extend(batch)
        total = page.get("totalRecords", len(records))
        offset += PAGE_SIZE
        if offset >= total or not batch:
            break
    return records


def record_name(record):
    """Pull a 'LAST, FIRST' key out of a SAM exclusion record."""
    ind = (record.get("exclusionIdentification", {})
           or record.get("entity", {}) or {})
    last = (ind.get("lastName") or record.get("lastName") or "").strip().upper()
    first = (ind.get("firstName") or record.get("firstName") or "").strip().upper()
    if not last and record.get("name"):
        # Fallback: a single name field "LAST, FIRST ..."
        parts = record["name"].upper().split(",")
        last = parts[0].strip()
        first = parts[1].strip().split(" ")[0] if len(parts) > 1 else ""
    return last, first


def screen_roster():
    if not RAW.exists():
        raise SystemExit(
            "No local SAM data. Run without --screen first to download it.")
    records = json.loads(RAW.read_text(encoding="utf-8"))

    index = defaultdict(list)
    for rec in records:
        last, first = record_name(rec)
        if last:
            index[(last, first)].append(rec)
            index[(last, "")].append(rec)   # allow last-name-only match

    people = read_csv(EMPLOYEE_DATA)
    flagged = []
    for person in people:
        last = person["last_name"].strip().upper()
        first = person["first_name"].strip().upper()
        hits = index.get((last, first)) or index.get((last, ""))
        if hits:
            flagged.append((person, hits))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "SAM.gov FEDERAL EXCLUSIONS - SCREENING SUMMARY",
        "=" * 60,
        "Generated: {}".format(date.today().isoformat()),
        "Source:    https://open.gsa.gov/api/exclusions-api/",
        "Records:   {} active individual exclusions".format(len(records)),
        "People:    {}".format(len(people)),
        "Flagged:   {}".format(len(flagged)),
        "",
        "A name match is a LEAD, not proof. SAM records carry no SSN; confirm",
        "identity (see v_7 NPPES) and the record itself before any action.",
        "",
    ]
    for person, hits in flagged:
        lines.append("  {} {} {}  -> {} SAM record(s)".format(
            person["employee_id"], person["first_name"],
            person["last_name"], len(hits)))
    if not flagged:
        lines.append("  No name matches against active SAM individual exclusions.")
    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("Screened {} people against {} SAM records: {} flagged.".format(
        len(people), len(records), len(flagged)))
    print("  Output: {}".format(SUMMARY_FILE))


def main():
    argv = sys.argv[1:]
    if "--screen" in argv:
        screen_roster()
        return

    try:
        api_key = get_api_key(argv)
    except SamKeyMissing as exc:
        print(exc)
        raise SystemExit(1)

    print("Downloading active individual exclusions from SAM.gov ...")
    records = fetch_all(api_key)
    RAW.write_text(json.dumps(records), encoding="utf-8")
    print("Saved {} records to {}".format(len(records), RAW.name))
    print("Now run:  python download_sam.py --screen")


if __name__ == "__main__":
    main()
