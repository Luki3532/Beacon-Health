"""
v_7 - NPPES / NPI Registry identity confirmation.

WHAT THIS IS FOR
----------------
The exclusion lists in v_2 (OIG LEIE) and v_4 (Michigan MDHHS) carry no SSNs.
So when a name matches, you cannot prove from those files alone that the hit is
YOUR employee rather than a same-named stranger. That is the weak point in the
whole screen.

NPPES closes that gap. The National Plan and Provider Enumeration System is the
CMS registry of every provider's NPI. Its public Read API returns a provider's
taxonomy (for example "Radiologic Technologist"), practice city, and state.
That is enough to tell "Smith, J. - Radiologic Technologist - Battle Creek, MI"
apart from an unrelated Smith three states away, before anyone acts on a flag.

WHY THIS ONE CAN BE AUTOMATED
-----------------------------
Unlike ARRT, NPPES publishes a real, documented, keyless public API and invites
programmatic use:

    https://npiregistry.cms.hhs.gov/api-page

No API key, no login, no CAPTCHA. This queries it one person at a time, exactly
the way the API is meant to be used, and caches each response so re-runs do not
re-hit the service.

WHAT NPPES IS NOT
-----------------
CMS states plainly: "Issuance of an NPI does not ensure or validate that the
Health Care Provider is Licensed or Credentialed." So this confirms IDENTITY,
not credential currency. ARRT remains the source for whether the registration
is actually current. NPPES surrounds that answer; it does not replace it.

Usage:
    python lookup_npi.py                # all employees (cached after first run)
    python lookup_npi.py --limit 5      # first 5 only (good for a quick test)
    python lookup_npi.py --refresh      # ignore cache, re-query everyone
    python lookup_npi.py --offline      # use cache only, make no network calls
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EMPLOYEE_DATA = ROOT / "v_1" / "employee_data.csv"

OUTPUT = HERE / "output"
RESULTS = OUTPUT / "results"
CACHE = HERE / "_cache"
SUMMARY_FILE = OUTPUT / "FINDINGS_SUMMARY.txt"

API = "https://npiregistry.cms.hhs.gov/api/"
API_VERSION = "2.1"
PAGE_LIMIT = 50           # NPPES returns up to 200; 50 is plenty per name
REQUEST_PAUSE = 0.3       # be a polite client
TIMEOUT = 30

# A taxonomy is "relevant" if its description hints at radiology / imaging.
# Used only to rank matches, never to hide them.
RELEVANT_TAXONOMY = (
    "radiolog", "radiograph", "technolog", "imaging", "nuclear",
    "sonograph", "mammograph", "magnetic resonance", "computed tomography",
)


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def cache_path(employee_id):
    return CACHE / "{}.json".format(employee_id)


def query_nppes(first, last, state):
    """Call the NPPES Read API. Returns the parsed JSON dict, or raises."""
    params = {
        "version": API_VERSION,
        "first_name": first,
        "last_name": last,
        "enumeration_type": "NPI-1",   # individuals only
        "limit": PAGE_LIMIT,
    }
    if state:
        params["state"] = state
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url, headers={"User-Agent": "Beacon-credential-tracker/1.0"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode("utf-8"))


def taxonomy_is_relevant(description):
    low = (description or "").lower()
    return any(term in low for term in RELEVANT_TAXONOMY)


def summarize_result(person, payload):
    """Reduce an NPPES response to the facts that confirm identity."""
    matches = []
    for item in payload.get("results", []) or []:
        basic = item.get("basic", {})
        taxonomies = item.get("taxonomies", []) or []
        primary = next((t for t in taxonomies if t.get("primary")), None) \
            or (taxonomies[0] if taxonomies else {})
        address = next(
            (a for a in item.get("addresses", []) or []
             if a.get("address_purpose") == "LOCATION"),
            {},
        )
        desc = primary.get("desc", "")
        matches.append({
            "npi": item.get("number", ""),
            "name": "{} {}".format(
                basic.get("first_name", ""), basic.get("last_name", "")
            ).strip(),
            "taxonomy": desc,
            "relevant": taxonomy_is_relevant(desc),
            "city": address.get("city", ""),
            "state": address.get("state", ""),
            "status": basic.get("status", ""),
        })

    # Rank: radiology taxonomy first, then same-city, so the likely employee
    # surfaces at the top without discarding anything.
    want_city = (person.get("city", "") or "").lower()
    matches.sort(key=lambda m: (
        0 if m["relevant"] else 1,
        0 if m["city"].lower() == want_city else 1,
    ))
    return matches


def confidence(person, matches):
    """How strong is the identity confirmation? Reported, never acted on."""
    if not matches:
        return "NONE", "No NPI record found for this name/state."
    top = matches[0]
    same_state = top["state"].upper() == (person.get("state", "") or "").upper()
    same_city = top["city"].lower() == (person.get("city", "") or "").lower()
    if top["relevant"] and same_city:
        return "STRONG", "Radiology taxonomy and matching city."
    if top["relevant"] and same_state:
        return "LIKELY", "Radiology taxonomy and matching state."
    if same_city:
        return "POSSIBLE", "Matching city, but taxonomy is not imaging-related."
    return "WEAK", "Name match only; verify location and taxonomy by hand."


def write_person_file(person, matches, conf, reason):
    name = "{} {}".format(person["first_name"], person["last_name"])
    lines = [
        "NPI IDENTITY CONFIRMATION",
        "=" * 60,
        "Employee:   {} ({})".format(name, person["employee_id"]),
        "On file:    {}, {}  {}".format(
            person.get("city", ""), person.get("state", ""),
            person.get("credentials", "")
        ),
        "Confidence: {}  -  {}".format(conf, reason),
        "",
        "Source: NPPES NPI Registry (public API, no key).",
        "Note:   An NPI confirms identity, NOT that the credential is current.",
        "",
    ]
    if matches:
        lines.append("Candidate NPI records ({}):".format(len(matches)))
        lines.append("-" * 60)
        for m in matches:
            flag = "*" if m["relevant"] else " "
            lines.append("{} NPI {}  {}".format(flag, m["npi"], m["name"]))
            lines.append("    {}".format(m["taxonomy"] or "(no taxonomy)"))
            lines.append("    {}, {}   status={}".format(
                m["city"], m["state"], m["status"]))
            lines.append("")
        lines.append("* = taxonomy looks radiology/imaging related")
    else:
        lines.append("No NPI records returned for this name in this state.")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "{}.txt".format(person["employee_id"])).write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main():
    argv = sys.argv[1:]
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    refresh = "--refresh" in argv
    offline = "--offline" in argv

    people = read_csv(EMPLOYEE_DATA)
    if not people:
        raise SystemExit("Employee data not found: {}".format(EMPLOYEE_DATA))
    if limit:
        people = people[:limit]

    CACHE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    buckets = {"STRONG": [], "LIKELY": [], "POSSIBLE": [], "WEAK": [], "NONE": []}
    errors = []
    queried = cached = 0

    for person in people:
        eid = person["employee_id"]
        cp = cache_path(eid)
        payload = None

        if cp.exists() and not refresh:
            try:
                payload = json.loads(cp.read_text(encoding="utf-8"))
                cached += 1
            except (ValueError, OSError):
                payload = None

        if payload is None:
            if offline:
                errors.append("{} {} {} - no cache, offline".format(
                    eid, person["first_name"], person["last_name"]))
                continue
            try:
                payload = query_nppes(
                    person["first_name"], person["last_name"],
                    person.get("state", ""))
                cp.write_text(json.dumps(payload), encoding="utf-8")
                queried += 1
                time.sleep(REQUEST_PAUSE)
            except (urllib.error.URLError, urllib.error.HTTPError,
                    TimeoutError, ValueError) as exc:
                errors.append("{} {} {} - {}".format(
                    eid, person["first_name"], person["last_name"], exc))
                continue

        matches = summarize_result(person, payload)
        conf, reason = confidence(person, matches)
        buckets[conf].append((person, matches, conf, reason))
        write_person_file(person, matches, conf, reason)

    write_summary(people, buckets, errors, queried, cached)
    print("NPPES identity confirmation complete.")
    print("  People:   {}".format(len(people)))
    print("  Queried:  {}   Cached: {}".format(queried, cached))
    for level in ("STRONG", "LIKELY", "POSSIBLE", "WEAK", "NONE"):
        print("  {:<9} {}".format(level + ":", len(buckets[level])))
    if errors:
        print("  Errors:   {} (see summary)".format(len(errors)))
    print("  Output:   {}".format(SUMMARY_FILE))


def write_summary(people, buckets, errors, queried, cached):
    confirmed = sum(len(buckets[b]) for b in ("STRONG", "LIKELY"))
    lines = [
        "NPPES / NPI REGISTRY - IDENTITY CONFIRMATION SUMMARY",
        "=" * 64,
        "Generated:  {}".format(date.today().isoformat()),
        "Source:     https://npiregistry.cms.hhs.gov/api-page (public, no key)",
        "People:     {}".format(len(people)),
        "Queried:    {}   From cache: {}".format(queried, cached),
        "",
        "Purpose: confirm that a flagged name is really the employee, using",
        "taxonomy + practice location. An NPI does NOT prove the credential",
        "is current - that is ARRT's job. This only strengthens identity.",
        "",
        "CONFIDENCE BREAKDOWN",
        "-" * 64,
        "  STRONG    {:>3}   radiology taxonomy + matching city".format(len(buckets["STRONG"])),
        "  LIKELY    {:>3}   radiology taxonomy + matching state".format(len(buckets["LIKELY"])),
        "  POSSIBLE  {:>3}   city matches, taxonomy does not".format(len(buckets["POSSIBLE"])),
        "  WEAK      {:>3}   name only - confirm by hand".format(len(buckets["WEAK"])),
        "  NONE      {:>3}   no NPI record for this name/state".format(len(buckets["NONE"])),
        "",
        "Identity confirmed (STRONG or LIKELY): {} of {}".format(confirmed, len(people)),
        "",
    ]
    for level in ("STRONG", "LIKELY", "POSSIBLE", "WEAK", "NONE"):
        rows = buckets[level]
        if not rows:
            continue
        lines.append("{} ({})".format(level, len(rows)))
        lines.append("-" * 64)
        for person, matches, conf, reason in rows:
            top = matches[0] if matches else None
            detail = ""
            if top:
                detail = "  NPI {}  {}  {}, {}".format(
                    top["npi"], top["taxonomy"] or "(no taxonomy)",
                    top["city"], top["state"])
            lines.append("  {:<5} {} {}{}".format(
                person["employee_id"], person["first_name"],
                person["last_name"], detail))
        lines.append("")

    if errors:
        lines.append("LOOKUP ERRORS ({})".format(len(errors)))
        lines.append("-" * 64)
        lines.extend("  " + e for e in errors)
        lines.append("")

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
