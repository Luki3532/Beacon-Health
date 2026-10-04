"""Shared credential state: who is verified, who is due, who has lapsed.

The verification ledger is the source of truth. A credential counts as
verified only because a named person looked it up and recorded the result --
never because a date was generated, inherited, or assumed.

Statuses
--------
NEVER_VERIFIED  No one has verified this person yet. Due now.
LAPSED          Last verified valid-thru date is in the past.
DUE             Expires within the alert window.
CURRENT         Verified and not expiring soon. No action.

Nothing here contacts ARRT. This module only reasons about what has already
been recorded by a human.
"""

import csv
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROSTER = HERE.parent / "v_1" / "roster.csv"
EMPLOYEE_DATA = HERE.parent / "v_1" / "employee_data.csv"
MANAGERS = HERE.parent / "v_1" / "managers.csv"
LEDGER = HERE / "verification_log.csv"

WINDOW_DAYS = 30

LEDGER_FIELDS = [
    "logged_at",
    "employee_id",
    "last_name",
    "first_name",
    "outcome",
    "credentials",
    "valid_thru",
    "verified_on",
    "verified_by",
    "source",
    "notes",
]

# Outcomes a human can record after attempting a lookup.
OUTCOME_VERIFIED = "verified"
OUTCOME_DISCREPANCY = "discrepancy"
OUTCOME_NOT_FOUND = "not-found"
OUTCOMES = (OUTCOME_VERIFIED, OUTCOME_DISCREPANCY, OUTCOME_NOT_FOUND)

NEVER_VERIFIED = "NEVER_VERIFIED"
LAPSED = "LAPSED"
DUE = "DUE"
CURRENT = "CURRENT"

# Order the worklist by urgency, not alphabetically.
STATUS_RANK = {LAPSED: 0, DUE: 1, NEVER_VERIFIED: 2, CURRENT: 3}


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_valid_thru(text):
    """ARRT publishes month/year only. Treat it as the last day of that month."""
    month, year = (int(part) for part in text.strip().split("/"))
    return date(year, month, monthrange(year, month)[1])


def parse_iso(text):
    return datetime.strptime(text.strip(), "%Y-%m-%d").date()


def load_roster():
    roster = read_csv(ROSTER)
    if not roster:
        raise SystemExit(
            "Roster not found or empty: {}\nRun v_1/generate_data.py first.".format(ROSTER)
        )
    return roster


def load_manager_emails():
    return {row["manager"]: row["email"].strip() for row in read_csv(MANAGERS)}


def load_on_file_dates():
    """Dates from employee_data.csv.

    These are SYNTHETIC and have not been verified by anyone. They are shown
    on the worklist purely as a hint about when to expect a renewal. They
    never drive status.
    """
    return {row["employee_id"]: row for row in read_csv(EMPLOYEE_DATA)}


def load_ledger():
    return read_csv(LEDGER)


def latest_verifications(ledger):
    """Most recent successful verification per employee.

    The ledger is append-only, so a correction is recorded as a new row rather
    than an edit. Later rows win.
    """
    latest = {}
    for row in ledger:
        if row.get("outcome") != OUTCOME_VERIFIED:
            continue
        if not row.get("valid_thru"):
            continue
        employee_id = row["employee_id"]
        previous = latest.get(employee_id)
        if previous is None or row["logged_at"] >= previous["logged_at"]:
            latest[employee_id] = row
    return latest


def latest_attempts(ledger):
    """Most recent lookup per employee, whatever the outcome.

    A not-found or discrepancy result still proves someone looked. The
    worklist shows it so the same dead end is not silently re-walked.
    """
    latest = {}
    for row in ledger:
        employee_id = row["employee_id"]
        previous = latest.get(employee_id)
        if previous is None or row["logged_at"] >= previous["logged_at"]:
            latest[employee_id] = row
    return latest


def status_for(verification, today, window_days=WINDOW_DAYS):
    """Return (status, expiry, days_remaining) for one person."""
    if verification is None:
        return NEVER_VERIFIED, None, None

    expiry = parse_valid_thru(verification["valid_thru"])
    days = (expiry - today).days
    if days < 0:
        return LAPSED, expiry, days
    if days <= window_days:
        return DUE, expiry, days
    return CURRENT, expiry, days


def build_state(today=None, window_days=WINDOW_DAYS):
    """Full picture for every person on the roster."""
    today = today or date.today()
    roster = load_roster()
    on_file = load_on_file_dates()
    ledger = load_ledger()
    latest = latest_verifications(ledger)
    attempts = latest_attempts(ledger)

    state = []
    for person in roster:
        employee_id = person["employee_id"]
        verification = latest.get(employee_id)
        status, expiry, days = status_for(verification, today, window_days)

        state.append(
            {
                "employee_id": employee_id,
                "first_name": person["first_name"],
                "last_name": person["last_name"],
                "manager": person["manager"],
                "status": status,
                "expiry": expiry,
                "days": days,
                "verification": verification,
                "last_attempt": attempts.get(employee_id),
                "on_file": on_file.get(employee_id),
            }
        )

    state.sort(key=lambda row: (
        STATUS_RANK[row["status"]],
        row["expiry"] or date.max,
        row["last_name"],
        row["first_name"],
    ))
    return state


def full_name(row):
    return "{} {}".format(row["first_name"], row["last_name"])


def manager_display(manager):
    last, first = [part.strip() for part in manager.split(",", 1)]
    return "{} {}".format(first, last)


def describe(row):
    """One-line status summary."""
    if row["status"] == NEVER_VERIFIED:
        attempt = row.get("last_attempt")
        if attempt:
            return "not yet verified - last lookup came back {}".format(attempt["outcome"])
        return "never verified"
    if row["status"] == LAPSED:
        return "LAPSED {} days ago (valid thru {:%m/%d/%Y})".format(-row["days"], row["expiry"])
    if row["status"] == DUE:
        return "expires in {} days ({:%m/%d/%Y})".format(row["days"], row["expiry"])
    return "current until {:%m/%d/%Y} ({} days)".format(row["expiry"], row["days"])
