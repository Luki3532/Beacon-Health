"""
v_6 - Credential screening and ARRT verification packets.

Reads the credentialing list, screens every person against the public
databases that permit automated access, and writes per-person findings plus a
findings summary.

WHAT IS AUTOMATED HERE
----------------------
  OIG LEIE          Federal exclusion list. OIG publishes a full CSV download
                    and states there are no plans for a public API, directing
                    bulk users to that file. This uses it as intended.

  MDHHS Michigan    Michigan Medicaid sanctioned provider list, published as a
                    spreadsheet. Same situation - no API, bulk file provided.

WHAT IS NOT AUTOMATED, AND WHY
------------------------------
ARRT registration status is NOT retrieved automatically. This is not a
limitation of the script - it is what ARRT asks for, in two places:

  1. https://www.arrt.org/robots.txt contains "Disallow: /Search".
     The credential lookup lives under /Search. That is ARRT stating, in the
     standard machine-readable way, that automated clients should not crawl
     it. This script CHECKS that file at runtime rather than taking my word
     for it, and reports what it finds.

  2. The ARRT Terms of Use say site content "is intended solely for personal,
     noncommercial use" and that you may not "copy, download, reproduce,
     modify, publish, distribute, transmit, transfer or create derivative
     works from the content, without first obtaining written permission."
     A stored, redistributed roster of scraped registration data is exactly
     that kind of derivative work.

Worth knowing: the same Terms EXPLICITLY permit the purpose Beacon has. Under
"Use of Registrant Information," the directory exists for "employers to verify
a technologist's certification and registration status (and valid-through
dates)." So the goal is sanctioned. It is the bulk automated extraction that
is not. Those are different things, and the difference is what this script is
built around.

So for ARRT, each person gets a verification packet: the exact lookup details
a human needs, and a line to write the result back. The evidence then has
clean provenance, which is the entire point in a surveyed environment.

To request broader access: ARRT, 651.687.0048

Usage:
    python screen.py
    python screen.py --limit 5
    python screen.py --refresh      # force re-download of source data
"""

import csv
import re
import sys
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ROSTER_FILE = HERE / "credentialing list"
OUTPUT = HERE / "output"
FINDINGS = OUTPUT / "findings"
SUMMARY_FILE = OUTPUT / "FINDINGS_SUMMARY.txt"
DATA = HERE / "_data"

LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
MI_URL = (
    "https://www.michigan.gov/mdhhs/-/media/Project/Websites/mdhhs/"
    "Assistance-Programs/Medicaid-BPHASA/MI-Sanctioned-Provider-List/"
    "MI_Sanctioned_Provider_List-XLSX.xlsx"
)

ARRT_ROBOTS_URL = "https://www.arrt.org/robots.txt"
ARRT_VERIFY_URL = "https://www.arrt.org/pages/verify-credentials"
ARRT_PHONE = "651.687.0048"

LEIE_VERIFY_URL = "https://exclusions.oig.hhs.gov/"
MI_CONTACT = "MDHHS-SanctionProviderList@michigan.gov"

LEIE_MAX_AGE_DAYS = 30
MI_MAX_AGE_DAYS = 7

USER_AGENT = "Beacon-Credentialing-Tool/1.0"

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

EXCEL_EPOCH = datetime(1899, 12, 30)
XL_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CELL_REF = re.compile(r"([A-Z]+)(\d+)")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def normalize(text):
    return " ".join((text or "").strip().upper().split())


def safe_filename(text):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def blank_if_zeros(raw):
    """LEIE pads empty fields with zeros instead of leaving them blank."""
    raw = (raw or "").strip()
    return "" if raw.strip("0") == "" else raw


def leie_date(raw):
    raw = blank_if_zeros(raw)
    if len(raw) == 8 and raw.isdigit():
        return "{}/{}/{}".format(raw[4:6], raw[6:8], raw[0:4])
    return raw or "(none)"


def excel_date(raw):
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
    """OIG search tips recommend trying each part of a hyphenated surname."""
    forms = [normalize(last_name)]
    for part in normalize(last_name).replace("-", " ").split():
        if part not in forms:
            forms.append(part)
    return forms


def manager_display(manager):
    if "," not in manager:
        return manager
    last, first = [p.strip() for p in manager.split(",", 1)]
    return "{} {}".format(first, last)


# --------------------------------------------------------------------------
# Minimal .xlsx reader (stdlib only, so this stays a single file)
# --------------------------------------------------------------------------

def _column_index(ref):
    match = CELL_REF.match(ref or "")
    if not match:
        return None
    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def read_xlsx_rows(path):
    with zipfile.ZipFile(path) as archive:
        try:
            shared_raw = archive.read("xl/sharedStrings.xml")
            shared = [
                "".join(n.text or "" for n in item.iter(XL_NS + "t"))
                for item in ElementTree.fromstring(shared_raw).findall(XL_NS + "si")
            ]
        except KeyError:
            shared = []

        sheets = sorted(n for n in archive.namelist() if n.startswith("xl/worksheets/sheet"))
        if not sheets:
            raise ValueError("No worksheet found in workbook.")
        raw = archive.read(sheets[0])

    sheet_data = ElementTree.fromstring(raw).find(XL_NS + "sheetData")
    if sheet_data is None:
        return

    for row in sheet_data.findall(XL_NS + "row"):
        values = []
        for cell in row.findall(XL_NS + "c"):
            index = _column_index(cell.get("r"))
            if index is None:
                index = len(values)

            kind = cell.get("t")
            if kind == "inlineStr":
                node = cell.find(XL_NS + "is")
                text = "".join(n.text or "" for n in node.iter(XL_NS + "t")) if node is not None else ""
            else:
                node = cell.find(XL_NS + "v")
                text = (node.text or "") if node is not None else ""
                if kind == "s" and text:
                    position = int(text)
                    text = shared[position] if position < len(shared) else ""

            while len(values) < index:
                values.append("")
            values.append(text.strip())
        yield values


# --------------------------------------------------------------------------
# ARRT compliance check - verified live, not asserted
# --------------------------------------------------------------------------

def check_arrt_robots():
    """Fetch ARRT's robots.txt and report whether /Search is crawlable.

    This is the one request this script makes to arrt.org, and robots.txt is
    the file explicitly published for automated clients to read. If ARRT ever
    opens /Search, this reports that instead of silently staying conservative.
    """
    result = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "url": ARRT_ROBOTS_URL,
        "search_disallowed": None,
        "raw": "",
        "error": "",
    }

    request = urllib.request.Request(ARRT_ROBOTS_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as error:
        result["error"] = str(error)
        return result

    result["raw"] = body.strip()

    # Walk the wildcard user-agent block and collect its Disallow rules.
    applies = False
    disallowed = []
    for line in body.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            # Rare but real: a value wrapped onto its own line.
            if applies and line.startswith("/"):
                disallowed.append(line)
            continue
        field, value = [p.strip() for p in line.split(":", 1)]
        field = field.lower()
        if field == "user-agent":
            applies = value == "*"
        elif field == "disallow" and applies and value:
            disallowed.append(value)

    result["search_disallowed"] = any(path.lower().startswith("/search") for path in disallowed)
    return result


# --------------------------------------------------------------------------
# Source data
# --------------------------------------------------------------------------

def stale(path, max_age_days):
    if not path.exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age > timedelta(days=max_age_days)


def find_existing(filename, siblings):
    """Reuse a copy already downloaded by an earlier version, if present."""
    for sibling in siblings:
        candidate = HERE.parent / sibling / filename
        if candidate.exists():
            return candidate
    return None


def ensure_source(filename, url, max_age_days, siblings, refresh, expect_zip=False):
    if not refresh:
        existing = find_existing(filename, siblings)
        if existing and not stale(existing, max_age_days):
            print("  Using existing {} from {}/".format(filename, existing.parent.name))
            return existing

    DATA.mkdir(exist_ok=True)
    local = DATA / filename

    if not refresh and local.exists() and not stale(local, max_age_days):
        print("  Using cached {}".format(filename))
        return local

    print("  Downloading {} ...".format(filename))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        data = response.read()

    if expect_zip and not data.startswith(b"PK"):
        raise SystemExit(
            "Expected a spreadsheet but got something else. The source URL may "
            "have moved:\n  {}".format(url)
        )

    local.write_bytes(data)
    print("    saved {:,} bytes".format(len(data)))
    return local


def load_leie(path):
    index = defaultdict(list)
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            last = normalize(row.get("LASTNAME", ""))
            first = normalize(row.get("FIRSTNAME", ""))
            if last and first:
                index[(last, first)].append(row)
    return index


def load_mi(path):
    rows = list(read_xlsx_rows(path))

    header_at = None
    for position, row in enumerate(rows):
        if any(normalize(cell) == "LAST NAME" for cell in row):
            header_at = position
            break
    if header_at is None:
        raise SystemExit("Could not find the header row in the MDHHS spreadsheet.")

    headers = [normalize(cell) for cell in rows[header_at]]
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
        record = {
            name: (row[position] if position < len(row) else "")
            for position, name in enumerate(headers)
        }
        last = normalize(record.get("LAST NAME", ""))
        first = normalize(record.get("FIRST NAME", ""))
        if last and first:
            total += 1
            index[(last, first)].append(record)
    return index, total


def search(index, last_name, first_name):
    first = normalize(first_name)
    found = []
    for surname in surname_forms(last_name):
        for record in index.get((surname, first), []):
            if record not in found:
                found.append(record)
    return found


# --------------------------------------------------------------------------
# Roster
# --------------------------------------------------------------------------

def load_roster():
    if not ROSTER_FILE.exists():
        raise SystemExit("Credentialing list not found: {}".format(ROSTER_FILE))

    people = []
    with open(ROSTER_FILE, encoding="utf-8-sig", errors="replace") as handle:
        lines = [line.rstrip("\n") for line in handle if line.strip()]

    for position, line in enumerate(lines):
        parts = [p.strip() for p in line.split("\t")]
        parts = [p for p in parts if p]
        if len(parts) < 2:
            continue
        if position == 0 and normalize(parts[0]).startswith("FIRST"):
            continue

        manager = parts[2] if len(parts) > 2 else ""
        if "," in manager:
            last, first = [p.strip() for p in manager.split(",", 1)]
            manager = "{}, {}".format(last, first)

        people.append({
            "employee_id": "E{:03d}".format(len(people) + 1),
            "first_name": parts[0],
            "last_name": parts[1],
            "manager": manager,
        })
    return people


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

def leie_section(matches):
    if not matches:
        return ["RESULT: NO MATCH", "",
                "This name does not appear in the federal exclusion list."]

    lines = [
        "RESULT: {} POSSIBLE NAME MATCH(ES) - REVIEW REQUIRED".format(len(matches)),
        "",
        "A name match is NOT proof of exclusion. The public file contains no",
        "SSNs, so identity cannot be confirmed from it.",
        "Verify at {} before any action.".format(LEIE_VERIFY_URL),
        "",
    ]
    for position, record in enumerate(matches, start=1):
        city = normalize(record.get("CITY", ""))
        state = normalize(record.get("STATE", ""))
        code = (record.get("EXCLTYPE") or "").strip()
        lines += [
            "--- Record {} of {} ---".format(position, len(matches)),
            "  Name on file:  {}, {} {}".format(
                normalize(record.get("LASTNAME", "")),
                normalize(record.get("FIRSTNAME", "")),
                normalize(record.get("MIDNAME", "")),
            ).rstrip(),
            "  Location:      {}".format(", ".join(p for p in (city, state) if p) or "(none)"),
            "  Specialty:     {}".format(normalize(record.get("SPECIALTY", "")) or "(none)"),
            "  General:       {}".format(normalize(record.get("GENERAL", "")) or "(none)"),
            "  NPI on file:   {}".format(blank_if_zeros(record.get("NPI")) or "(none)"),
            "  Excluded:      {}".format(leie_date(record.get("EXCLDATE", ""))),
            "  Reinstated:    {}".format(leie_date(record.get("REINDATE", ""))),
            "  Basis:         {} - {}".format(
                code or "(none)", EXCLUSION_TYPES.get(code, "see OIG record layout")),
            "",
        ]
    return lines


def mi_section(matches):
    if not matches:
        return ["RESULT: NO MATCH", "",
                "This name does not appear on the Michigan sanctioned provider list."]

    lines = [
        "RESULT: {} POSSIBLE NAME MATCH(ES) - REVIEW REQUIRED".format(len(matches)),
        "",
        "A name match is NOT proof of sanction. Confirm with MDHHS at",
        "{} before any action.".format(MI_CONTACT),
        "",
    ]
    for position, record in enumerate(matches, start=1):
        sources = [record.get("SANCTION SOURCE", ""), record.get("SANCTION SOURCE 2", "")]
        sources = [s.strip() for s in sources if s and s.strip()]
        lines += [
            "--- Record {} of {} ---".format(position, len(matches)),
            "  Name on file:  {}, {} {}".format(
                normalize(record.get("LAST NAME", "")),
                normalize(record.get("FIRST NAME", "")),
                normalize(record.get("MIDDLE NAME", "")),
            ).rstrip(),
            "  Entity:        {}".format(record.get("ENTITY NAME", "") or "(none)"),
            "  Category:      {}".format(record.get("PROVIDER CATEGORY", "") or "(none)"),
            "  City:          {}".format(record.get("CITY", "") or "(none)"),
            "  NPI on file:   {}".format(record.get("NPI#", "") or "(none)"),
            "  License #:     {}".format(record.get("LICENSE#", "") or "(none)"),
            "  Sanction date: {}".format(excel_date(record.get("SANCTION DATE1", ""))),
            "  Second date:   {}".format(excel_date(record.get("SANCTION DATE2", ""))),
            "  Source:        {}".format(", ".join(sources) or "(none)"),
            "  Reason:        {}".format(record.get("REASON", "") or "(none)"),
            "",
        ]
    return lines


def arrt_section(person, robots):
    name = "{} {}".format(person["first_name"], person["last_name"])

    if robots["error"]:
        status = "could not be checked ({})".format(robots["error"])
    elif robots["search_disallowed"]:
        status = 'robots.txt contains "Disallow: /Search"'
    elif robots["search_disallowed"] is False:
        status = "robots.txt does NOT disallow /Search (see note below)"
    else:
        status = "unknown"

    lines = [
        "RESULT: NOT RETRIEVED AUTOMATICALLY - human verification required",
        "",
        "ARRT policy check ({}): {}".format(robots["checked_at"][:10], status),
        "",
    ]

    if robots["search_disallowed"] is False and not robots["error"]:
        lines += [
            "NOTE: the Disallow rule was not found this run. That alone does not",
            "authorize bulk extraction - the ARRT Terms of Use separately limit",
            "site content to personal, noncommercial use and prohibit creating",
            "derivative works without written permission. Confirm with ARRT",
            "before changing this workflow.",
            "",
        ]

    lines += [
        "Beacon's PURPOSE here is expressly permitted. ARRT's Terms of Use,",
        'under "Use of Registrant Information," list verification "by employers',
        'to verify a technologist\'s certification and registration status (and',
        'valid-through dates)" as an approved use of the directory.',
        "",
        "What is not permitted is automated bulk extraction. So the lookup is",
        "done by a person, and the result is recorded below with their name on",
        "it. That is stronger evidence in a survey than scraped data, not",
        "weaker.",
        "",
        "VERIFICATION PACKET",
        "  Look up:     {}".format(name),
        "  Where:       {}".format(ARRT_VERIFY_URL),
        "  Employee ID: {}".format(person["employee_id"]),
        "  Manager:     {}".format(manager_display(person["manager"])),
        "",
        "  Record the result here:",
        "    Credentials  ....................................",
        "    Valid through (MM/YYYY)  ........................",
        "    Verified by  ....................................",
        "    Date verified  ..................................",
        "",
        "  Broader/bulk employer access: ARRT {}".format(ARRT_PHONE),
    ]
    return lines


def write_findings(person, leie_matches, mi_matches, robots):
    name = "{} {}".format(person["first_name"], person["last_name"])
    path = FINDINGS / "{}_{}_{}.txt".format(
        person["employee_id"],
        safe_filename(person["last_name"]),
        safe_filename(person["first_name"]),
    )

    screened_hits = len(leie_matches) + len(mi_matches)
    verdict = "REVIEW REQUIRED" if screened_hits else "CLEAR on screened sources"

    lines = [
        "CREDENTIAL SCREENING FINDINGS",
        "=" * 68,
        "Name:        {}".format(name),
        "Employee ID: {}".format(person["employee_id"]),
        "Manager:     {}".format(manager_display(person["manager"])),
        "Screened:    {:%m/%d/%Y}".format(date.today()),
        "",
        "SCREENING VERDICT: {}  (federal {}, Michigan {})".format(
            verdict, len(leie_matches), len(mi_matches)),
        "ARRT REGISTRATION: pending human verification - see source 3",
        "",
        "-" * 68,
        "SOURCE 1 of 3: OIG LEIE (federal exclusion list)   [AUTOMATED]",
        "-" * 68,
    ]
    lines += leie_section(leie_matches)
    lines += [
        "",
        "-" * 68,
        "SOURCE 2 of 3: Michigan Medicaid sanctions (MDHHS) [AUTOMATED]",
        "-" * 68,
    ]
    lines += mi_section(mi_matches)
    lines += [
        "",
        "-" * 68,
        "SOURCE 3 of 3: ARRT registration status            [MANUAL]",
        "-" * 68,
    ]
    lines += arrt_section(person, robots)
    lines += [
        "",
        "-" * 68,
        "Exclusion screening is not credential verification. A clear screening",
        "result does not mean a registration is current.",
        "Contains real employee data - keep local, do not share or commit.",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_summary(results, robots, counts, elapsed):
    flagged = [r for r in results if r["leie"] or r["mi"]]

    if robots["error"]:
        arrt_line = "could not be checked this run ({})".format(robots["error"])
    elif robots["search_disallowed"]:
        arrt_line = 'confirmed - robots.txt contains "Disallow: /Search"'
    else:
        arrt_line = "Disallow rule NOT found this run - see per-person findings"

    lines = [
        "FINDINGS SUMMARY",
        "=" * 68,
        "Run date:  {:%m/%d/%Y}".format(date.today()),
        "People:    {}".format(len(results)),
        "Elapsed:   {:.1f}s".format(elapsed),
        "",
        "SOURCES",
        "  OIG LEIE (federal)          AUTOMATED   {:,} individuals indexed".format(
            counts["leie"]),
        "  MDHHS Michigan sanctions    AUTOMATED   {:,} individuals indexed".format(
            counts["mi"]),
        "  ARRT registration status    MANUAL      not retrieved - see below",
        "",
        "RESULTS",
        "  Flagged for review:         {}".format(len(flagged)),
        "  Clear on screened sources:  {}".format(len(results) - len(flagged)),
        "  Awaiting ARRT verification: {}".format(len(results)),
        "",
        "=" * 68,
        "WHY ARRT IS NOT AUTOMATED",
        "=" * 68,
        "ARRT policy check: {}".format(arrt_line),
        "Checked at: {}".format(robots["checked_at"]),
        "",
        "Two independent reasons, both from ARRT:",
        "",
        '  1. robots.txt publishes "Disallow: /Search". The credential lookup',
        "     lives there. That is the standard machine-readable way a site",
        "     tells automated clients to stay out.",
        "",
        '  2. The Terms of Use limit site content to "personal, noncommercial',
        '     use" and prohibit creating derivative works without written',
        "     permission. A stored roster of extracted registration data is",
        "     such a work.",
        "",
        "Beacon's purpose is NOT the problem. ARRT's Terms expressly permit",
        'employers to verify "certification and registration status (and',
        'valid-through dates)." The permitted path is a person doing the',
        "lookup, which each findings file is set up for.",
        "",
        "For bulk employer access, contact ARRT at {}.".format(ARRT_PHONE),
        "",
        "=" * 68,
        "FLAGGED FOR REVIEW",
        "=" * 68,
    ]

    if not flagged:
        lines += [
            "",
            "No name matches on either screened database.",
            "",
            "For a compliant workforce this is the expected result. It means the",
            "screening ran and found nothing, not that it failed to run - the",
            "indexed counts above are what confirm the search was live.",
        ]
    else:
        lines.append("")
        for item in flagged:
            lines.append("  {}  {:<28}  federal:{}  michigan:{}".format(
                item["employee_id"], item["name"], item["leie"], item["mi"]))
        lines += [
            "",
            "None of these are confirmed. Neither public file contains SSNs, so",
            "a name match cannot establish identity. Compare specialty, city,",
            "state, and NPI, then confirm with the issuing agency:",
            "  Federal:  {}".format(LEIE_VERIFY_URL),
            "  Michigan: {}".format(MI_CONTACT),
        ]

    lines += [
        "",
        "=" * 68,
        "ALL PEOPLE",
        "=" * 68,
        "",
    ]
    for item in results:
        marker = "REVIEW" if (item["leie"] or item["mi"]) else "clear "
        lines.append("  {}  {:<6}  {:<28}  ARRT: pending  {}".format(
            marker, item["employee_id"], item["name"], item["file"]))

    lines += [
        "",
        "-" * 68,
        "Contains real employee data - keep local, do not share or commit.",
    ]

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------

def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    refresh = "--refresh" in sys.argv

    started = datetime.now()

    print("Checking ARRT access policy ...")
    robots = check_arrt_robots()
    if robots["error"]:
        print("  Could not reach robots.txt: {}".format(robots["error"]))
        print("  Treating ARRT as manual-only.")
    elif robots["search_disallowed"]:
        print('  robots.txt: "Disallow: /Search" -> ARRT handled manually.')
    else:
        print("  robots.txt: no /Search disallow found.")
        print("  Still manual - Terms of Use separately restrict bulk use.")

    print("\nPreparing source data ...")
    leie_path = ensure_source("leie.csv", LEIE_URL, LEIE_MAX_AGE_DAYS, ["v_2"], refresh)
    mi_path = ensure_source("mi_sanctions.xlsx", MI_URL, MI_MAX_AGE_DAYS, ["v_4"],
                            refresh, expect_zip=True)

    print("\nIndexing ...")
    leie_index = load_leie(leie_path)
    mi_index, mi_total = load_mi(mi_path)
    print("  Federal:  {:,} distinct excluded individuals".format(len(leie_index)))
    print("  Michigan: {:,} sanctioned individuals".format(mi_total))

    roster = load_roster()
    if limit:
        roster = roster[:limit]
    print("  Roster:   {} people\n".format(len(roster)))

    FINDINGS.mkdir(parents=True, exist_ok=True)

    results = []
    for position, person in enumerate(roster, start=1):
        name = "{} {}".format(person["first_name"], person["last_name"])
        print("[{}/{}] {} ... ".format(position, len(roster), name), end="", flush=True)

        leie_matches = search(leie_index, person["last_name"], person["first_name"])
        mi_matches = search(mi_index, person["last_name"], person["first_name"])
        path = write_findings(person, leie_matches, mi_matches, robots)

        if leie_matches or mi_matches:
            print("REVIEW (federal {}, michigan {})".format(len(leie_matches), len(mi_matches)))
        else:
            print("clear")

        results.append({
            "employee_id": person["employee_id"],
            "name": name,
            "leie": len(leie_matches),
            "mi": len(mi_matches),
            "file": path.name,
        })

    elapsed = (datetime.now() - started).total_seconds()
    write_summary(results, robots,
                  {"leie": len(leie_index), "mi": mi_total}, elapsed)

    flagged = sum(1 for r in results if r["leie"] or r["mi"])
    print("\nDone in {:.1f}s.".format(elapsed))
    print("  Findings: {}  ({} files)".format(FINDINGS, len(results)))
    print("  Summary:  {}".format(SUMMARY_FILE))
    print("  Flagged for review: {}".format(flagged))
    print("  Awaiting ARRT verification: {}".format(len(results)))


if __name__ == "__main__":
    main()
