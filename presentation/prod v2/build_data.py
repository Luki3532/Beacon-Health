"""
Generate assets/data.js for the PeopleSoft-style credentialing console.

Reads the real pipeline outputs and bakes them into a JavaScript file so the
mockup opens with a double-click. No server, no fetch(), no dependencies.

Sources
-------
  v_1/roster.csv                    employee -> manager
  v_1/employee_data.csv             credentials, valid-through, CE, CQR
  v_1/managers.csv                  manager -> email
  v_5/verification_log.csv          who verified what, and when
  v_6/output/FINDINGS_SUMMARY.txt   exclusion-screening flags

Status logic is ported from v_5/credential_state.py so the console agrees with
the alert job rather than inventing its own rules.

Usage:
    python build_data.py
    python build_data.py --as-of 2026-11-15
"""

import csv
import json
import re
import sys
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

ROSTER = ROOT / "v_1" / "roster.csv"
EMPLOYEE_DATA = ROOT / "v_1" / "employee_data.csv"
MANAGERS = ROOT / "v_1" / "managers.csv"
LEDGER = ROOT / "v_5" / "verification_log.csv"
FINDINGS = ROOT / "v_6" / "output" / "FINDINGS_SUMMARY.txt"

# Real pipeline downloads, used to report data-source connection state.
LEIE_FILE = ROOT / "v_2" / "leie.csv"
MI_FILE = ROOT / "v_4" / "mi_sanctions.xlsx"
NPI_CACHE = ROOT / "v_7" / "_cache"
NPI_SUMMARY = ROOT / "v_7" / "output" / "FINDINGS_SUMMARY.txt"
NPI_IMPORT = ROOT / "v_7" / "active" / "credentialing_list.csv"
SAM_FILE = ROOT / "v_8" / "sam_exclusions.json"
IN_CSV = ROOT / "v_9" / "in_sanctions.csv"
IN_XLSX = ROOT / "v_9" / "in_sanctions.xlsx"

OUT = HERE / "assets" / "data.js"

WINDOW_DAYS = 30

LAPSED = "LAPSED"
DUE = "DUE"
NEVER_VERIFIED = "NEVER_VERIFIED"
CURRENT = "CURRENT"

STATUS_RANK = {LAPSED: 0, DUE: 1, NEVER_VERIFIED: 2, CURRENT: 3}

# "  E059  Carrie Wilson   federal:2  michigan:0"
FLAGGED_LINE = re.compile(
    r"^\s+(E\d{3})\s+(.+?)\s+federal:(\d+)\s+michigan:(\d+)\s*$"
)


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def valid_thru_date(text):
    """ARRT publishes month/year. Treat it as the last day of that month."""
    month, year = (int(part) for part in text.strip().split("/"))
    return date(year, month, monthrange(year, month)[1])


def status_for(valid_thru, today, window_days=WINDOW_DAYS):
    """Return (status, days_remaining). Mirrors v_5/credential_state.py."""
    if not valid_thru:
        return NEVER_VERIFIED, None
    expiry = valid_thru_date(valid_thru)
    days = (expiry - today).days
    if days < 0:
        return LAPSED, days
    if days <= window_days:
        return DUE, days
    return CURRENT, days


def manager_key(name):
    """Normalize 'McIntyre,Kathryn E' -> 'McIntyre, Kathryn E'."""
    name = (name or "").strip()
    if "," not in name:
        return name
    last, first = [part.strip() for part in name.split(",", 1)]
    return "{}, {}".format(last, first)


def manager_display(name):
    name = manager_key(name)
    if "," not in name:
        return name
    last, first = [part.strip() for part in name.split(",", 1)]
    return "{} {}".format(first, last)


def load_flagged():
    """Employee IDs with exclusion-screening hits, from the v_6 summary."""
    flagged = {}
    if not FINDINGS.exists():
        return flagged

    inside = False
    for line in FINDINGS.read_text(encoding="utf-8").splitlines():
        if line.startswith("FLAGGED FOR REVIEW"):
            inside = True
            continue
        if inside and line.startswith("="):
            continue
        if inside and line.startswith("ALL PEOPLE"):
            break

        match = FLAGGED_LINE.match(line)
        if match and inside:
            employee_id, _, federal, michigan = match.groups()
            flagged[employee_id] = {
                "federal": int(federal),
                "michigan": int(michigan),
            }
    return flagged


def load_verifications():
    """Latest ledger entry per employee, and latest successful verification."""
    attempts = {}
    verified = {}
    for row in read_csv(LEDGER):
        employee_id = row.get("employee_id", "")
        if not employee_id:
            continue
        previous = attempts.get(employee_id)
        if previous is None or row["logged_at"] >= previous["logged_at"]:
            attempts[employee_id] = row
        if row.get("outcome") == "verified" and row.get("valid_thru"):
            prior = verified.get(employee_id)
            if prior is None or row["logged_at"] >= prior["logged_at"]:
                verified[employee_id] = row
    return attempts, verified


def file_facts(path):
    """(exists, record_count, 'MM/DD/YYYY' last-modified) for a data file."""
    if not path.exists():
        return False, None, ""
    stamp = datetime.fromtimestamp(path.stat().st_mtime)
    records = None
    if path.suffix.lower() == ".csv":
        # Count data rows without loading the whole file into memory.
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            records = max(0, sum(1 for _ in handle) - 1)
    return True, records, "{:%m/%d/%Y}".format(stamp)


def load_sources(ledger_rows):
    """
    Data-source connection state for the Integrations page.

    Every entry reflects the real pipeline: the two public exclusion files are
    genuinely downloaded, the ledger is a real CSV, and ARRT has no connection
    because there is no public API and the lookup sits behind a CAPTCHA. The
    page is where a future ARRT feed (import or API) would be wired in.
    """
    leie_ok, leie_rows, leie_when = file_facts(LEIE_FILE)
    mi_ok, _, mi_when = file_facts(MI_FILE)

    npi_ok = NPI_SUMMARY.exists()
    npi_cached = len(list(NPI_CACHE.glob("*.json"))) if NPI_CACHE.exists() else 0
    npi_when = file_facts(NPI_SUMMARY)[2] if npi_ok else ""
    npi_import_ok, npi_import_rows, npi_import_when = file_facts(NPI_IMPORT)
    sam_ok, _, sam_when = file_facts(SAM_FILE)
    in_ok = IN_CSV.exists() or IN_XLSX.exists()
    in_when = file_facts(IN_CSV if IN_CSV.exists() else IN_XLSX)[2] if in_ok else ""

    return [
        {
            "key": "arrt",
            "name": "ARRT - American Registry of Radiologic Technologists",
            "kind": "Primary source verification",
            "status": "MANUAL",
            "statusLabel": "Manual lookup",
            "mode": "Person verifies at arrt.org, records result in ledger",
            "format": "Web form (CAPTCHA-protected)",
            "records": None,
            "lastSync": "",
            "canApi": True,
            "canImport": True,
            "docsUrl": "https://www.arrt.org",
            "docsLabel": "arrt.org",
            "note": ("No public API, and the credential lookup is behind a "
                     "CAPTCHA that its terms forbid automating. Employer "
                     "verification itself is permitted, so a data feed must be "
                     "arranged with ARRT directly (651.687.0048). When that is "
                     "in place, connect it here - the rest of the console is "
                     "already wired for it."),
        },
        {
            "key": "leie",
            "name": "OIG LEIE - Federal Exclusions",
            "kind": "Exclusion screening",
            "status": "CONNECTED" if leie_ok else "DISCONNECTED",
            "statusLabel": "Automated download" if leie_ok else "Not downloaded",
            "mode": "Public bulk file, refreshed monthly by OIG",
            "format": "CSV",
            "records": leie_rows,
            "lastSync": leie_when,
            "canApi": False,
            "canImport": True,
            "docsUrl": "https://oig.hhs.gov/exclusions/leie-database-supplement-downloads/",
            "docsLabel": "oig.hhs.gov",
            "note": ("Free, public, no key required. A name match is a lead, "
                     "not proof - the file carries no SSNs, so identity must be "
                     "confirmed before any action."),
        },
        {
            "key": "mdhhs",
            "name": "Michigan MDHHS - Medicaid Provider Sanctions",
            "kind": "Exclusion screening",
            "status": "CONNECTED" if mi_ok else "DISCONNECTED",
            "statusLabel": "Imported file" if mi_ok else "Not imported",
            "mode": "Public spreadsheet published by the State of Michigan",
            "format": "XLSX",
            "records": None,
            "lastSync": mi_when,
            "canApi": False,
            "canImport": True,
            "docsUrl": "https://www.michigan.gov/mdhhs/doing-business/providers/providers/",
            "docsLabel": "michigan.gov",
            "note": ("Published as a spreadsheet, so this is the model for the "
                     "Import XLSX path. Same identity caveat as the federal "
                     "list applies."),
        },
        {
            "key": "nppes",
            "name": "NPPES - NPI Registry (CMS)",
            "kind": "Identity confirmation",
            "status": "CONNECTED" if (npi_ok or npi_import_ok) else "AVAILABLE",
            "statusLabel": ("Roster imported" if npi_import_ok
                            else ("Automated API" if npi_ok
                                  else "Ready - not yet run")),
            "mode": ("Imported roster CSV (v_7/active), then a keyless public API "
                     "query per employee (v_7)"),
            "format": "CSV / XLSX + REST API",
            "records": (npi_import_rows if npi_import_ok
                        else (npi_cached if npi_ok else None)),
            "lastSync": npi_import_when or npi_when,
            "canApi": True,
            "apiLabel": "Run API Script",
            "canImport": True,
            "importLabel": "Import CSV/XLSX",
            "docsUrl": "https://npiregistry.cms.hhs.gov/api-page",
            "docsLabel": "npiregistry.cms.hhs.gov",
            "note": ("Confirms IDENTITY (taxonomy + practice location), which is "
                     "the piece the exclusion lists cannot give you - they carry "
                     "no SSNs. No key, no CAPTCHA; CMS invites programmatic use. "
                     "A roster is imported as CSV/XLSX (the demo ships with "
                     "v_7/active/credentialing_list.xlsx already uploaded, with "
                     "a parser mirror CSV), then "
                     "the API script resolves each person. An NPI does not prove "
                     "a credential is current - that stays ARRT's job."),
        },
        {
            "key": "sam",
            "name": "SAM.gov - Federal Exclusions (GSA)",
            "kind": "Exclusion screening",
            "status": "CONNECTED" if sam_ok else "DISCONNECTED",
            "statusLabel": "API key configured" if sam_ok else "Needs free API key",
            "mode": "Government-wide debarments via the public Exclusions API (v_8)",
            "format": "REST / JSON",
            "records": None,
            "lastSync": sam_when,
            "canApi": True,
            "canImport": False,
            "docsUrl": "https://open.gsa.gov/api/exclusions-api/",
            "docsLabel": "open.gsa.gov",
            "note": ("Broader than OIG LEIE - every federal agency, not just "
                     "healthcare. The API is open to automation but gated by a "
                     "free key (sam.gov -> Account Details -> API Key). The "
                     "backend is built; set SAM_API_KEY and it runs."),
        },
        {
            "key": "indiana",
            "name": "Indiana Medicaid - Provider Sanctions",
            "kind": "Exclusion screening",
            "status": "CONNECTED" if in_ok else "DISCONNECTED",
            "statusLabel": "File imported" if in_ok else "Awaiting import",
            "mode": "State list downloaded by hand, then screened (v_9)",
            "format": "CSV / XLSX",
            "records": None,
            "lastSync": in_when,
            "canApi": False,
            "canImport": True,
            "docsUrl": ("https://www.in.gov/medicaid/providers/provider-references/"
                        "termination-for-cause-and-provider-sanctions/"),
            "docsLabel": "in.gov/medicaid",
            "note": ("Beacon's home state, and a gap OIG and Michigan miss. "
                     "Indiana posts the list as a document, not a feed, so this "
                     "is an import: save the file in v_9 and screen. A name "
                     "match is a lead, not proof."),
        },
        {
            "key": "inpla",
            "name": "Indiana PLA - License Verification",
            "kind": "License verification",
            "status": "MANUAL",
            "statusLabel": "Manual lookup",
            "mode": "State license portal, verified by a person",
            "format": "Web portal",
            "records": None,
            "lastSync": "",
            "canApi": False,
            "canImport": True,
            "docsUrl": "https://mylicense.in.gov/everification/",
            "docsLabel": "mylicense.in.gov",
            "note": ("A second primary source alongside ARRT for techs who also "
                     "hold an Indiana state license. The portal is a web lookup "
                     "(no open API), so it is verified by a person and recorded "
                     "in the ledger - the same disciplined path as ARRT. If the "
                     "state provides an export, import it here."),
        },
        {
            "key": "ledger",
            "name": "Verification Ledger",
            "kind": "Internal record",
            "status": "INTERNAL",
            "statusLabel": "Local file",
            "mode": "Append-only; one row per lookup a person performs",
            "format": "CSV",
            "records": len(ledger_rows),
            "lastSync": file_facts(LEDGER)[2],
            "canApi": False,
            "canImport": False,
            "docsUrl": "",
            "docsLabel": "",
            "note": ("This is the system of record for who verified what, and "
                     "when. Entries are never edited; a correction is a new "
                     "row."),
        },
    ]


def main():
    argv = sys.argv[1:]

    today = date.today()
    if "--as-of" in argv:
        raw = argv[argv.index("--as-of") + 1]
        today = datetime.strptime(raw, "%Y-%m-%d").date()

    roster = read_csv(ROSTER)
    if not roster:
        raise SystemExit("Roster not found: {}".format(ROSTER))

    detail = {row["employee_id"]: row for row in read_csv(EMPLOYEE_DATA)}
    emails = {manager_key(row["manager"]): row["email"].strip()
              for row in read_csv(MANAGERS)}
    attempts, verified = load_verifications()
    flagged = load_flagged()

    employees = []
    for person in roster:
        employee_id = person["employee_id"]
        data = detail.get(employee_id, {})
        first, last = person["first_name"], person["last_name"]

        valid_thru = data.get("valid_thru", "").strip()
        status, days = status_for(valid_thru, today)

        attempt = attempts.get(employee_id)
        success = verified.get(employee_id)
        hits = flagged.get(employee_id)

        employees.append({
            "id": employee_id,
            "first": first,
            "last": last,
            "name": "{} {}".format(first, last),
            "sortName": "{}, {}".format(last, first),
            "manager": manager_key(person["manager"]),
            "managerName": manager_display(person["manager"]),
            "city": data.get("city", ""),
            "state": data.get("state", ""),
            "zip": data.get("zip", ""),
            "country": data.get("country", ""),
            "credentials": data.get("credentials", ""),
            "validThru": valid_thru,
            "ceStart": data.get("ce_biennium_start", ""),
            "ceEnd": data.get("ce_biennium_end", ""),
            "cqr": data.get("cqr_periods", ""),
            "dataSource": data.get("data_source", ""),
            "status": status,
            "days": days,
            "rank": STATUS_RANK[status],
            "lastOutcome": attempt.get("outcome", "") if attempt else "",
            "lastVerifiedOn": attempt.get("verified_on", "") if attempt else "",
            "lastVerifiedBy": attempt.get("verified_by", "") if attempt else "",
            "lastSource": attempt.get("source", "") if attempt else "",
            "lastNotes": attempt.get("notes", "") if attempt else "",
            "ledgerValidThru": success.get("valid_thru", "") if success else "",
            "screenFederal": hits["federal"] if hits else 0,
            "screenMichigan": hits["michigan"] if hits else 0,
            "flagged": bool(hits),
        })

    employees.sort(key=lambda row: (row["rank"], row["sortName"]))

    managers = []
    for key in sorted({row["manager"] for row in employees}):
        reports = [row for row in employees if row["manager"] == key]
        managers.append({
            "key": key,
            "name": manager_display(key),
            "email": emails.get(key, ""),
            "total": len(reports),
            "lapsed": sum(1 for r in reports if r["status"] == LAPSED),
            "due": sum(1 for r in reports if r["status"] == DUE),
            "flagged": sum(1 for r in reports if r["flagged"]),
        })

    counts = {
        "total": len(employees),
        "lapsed": sum(1 for r in employees if r["status"] == LAPSED),
        "due": sum(1 for r in employees if r["status"] == DUE),
        "current": sum(1 for r in employees if r["status"] == CURRENT),
        "never": sum(1 for r in employees if r["status"] == NEVER_VERIFIED),
        "flagged": sum(1 for r in employees if r["flagged"]),
        # Two different numbers, deliberately kept apart:
        #   verified      - employees with a successful lookup on record
        #   ledgerEntries - employees with ANY lookup on record, including
        #                   not-found and discrepancy. The audit log shows
        #                   these, because a failed lookup is evidence too.
        "verified": len(verified),
        "ledgerEntries": len(attempts),
    }

    payload = {
        "asOf": today.isoformat(),
        "asOfDisplay": "{:%m/%d/%Y}".format(today),
        "windowDays": WINDOW_DAYS,
        # Fictional-name mode has been retired for this workspace.
        # Keep the key present but null so older UI code sees it as disabled.
        "fictional": None,
        "counts": counts,
        "employees": employees,
        "managers": managers,
        "sources": load_sources(read_csv(LEDGER)),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "// GENERATED by build_data.py - do not edit by hand.\n"
        "// Source: v_1 CSVs, v_5 ledger, v_6 screening summary.\n"
        "// Regenerate: python build_data.py\n"
        "const PS_DATA = {};\n".format(json.dumps(payload, indent=2)),
        encoding="utf-8",
    )

    print("Wrote {}".format(OUT))
    print("  As of:    {:%m/%d/%Y}  (window {} days)".format(today, WINDOW_DAYS))
    print("  Names:    provided roster only")
    print("  Employees:{:>5}".format(counts["total"]))
    print("    lapsed: {:>5}".format(counts["lapsed"]))
    print("    due:    {:>5}".format(counts["due"]))
    print("    current:{:>5}".format(counts["current"]))
    print("    never:  {:>5}".format(counts["never"]))
    print("  Flagged:  {:>5}".format(counts["flagged"]))
    print("  Managers: {:>5}".format(len(managers)))
    for manager in managers:
        note = "" if manager["email"] else "   <- NO EMAIL ON FILE"
        print("    {:<24} {:>3} reports{}".format(
            manager["name"], manager["total"], note))


if __name__ == "__main__":
    main()
