"""Record the result of a human credential verification.

Appends one row to the verification ledger. The ledger is append-only: a
correction is a new row, never an edit, so the history of who checked what and
when stays intact.

Usage:
    python record_verification.py E001 --valid-thru 10/2027 \
        --credentials "R.T.(R)(ARRT)" --by "Teresa Covarrubias Gonzalez"

    python record_verification.py E022 --outcome not-found --by "Teresa G" \
        --notes "No record returned; following up with technologist"

Options:
    --valid-thru MM/YYYY   Required when the outcome is 'verified'
    --credentials TEXT     Credential string exactly as shown on the record
    --by NAME              Who performed the lookup (required)
    --on YYYY-MM-DD        Date of the lookup (defaults to today)
    --outcome WORD         verified | discrepancy | not-found
    --source TEXT          Where it was verified (defaults to the ARRT directory)
    --notes TEXT           Anything worth keeping with the record
"""

import csv
import sys
from datetime import date, datetime

import credential_state as state

DEFAULT_SOURCE = "ARRT online directory (manual lookup)"


def fail(message):
    raise SystemExit("ERROR: {}".format(message))


def take_option(argv, name, default=None):
    if name not in argv:
        return default
    position = argv.index(name) + 1
    if position >= len(argv):
        fail("{} needs a value.".format(name))
    return argv[position]


def validate_valid_thru(text):
    try:
        parsed = state.parse_valid_thru(text)
    except (ValueError, IndexError):
        fail("--valid-thru must look like MM/YYYY, for example 10/2027. Got: {}".format(text))

    month, year = (int(part) for part in text.strip().split("/"))
    if not 1 <= month <= 12:
        fail("--valid-thru month must be 1-12. Got: {}".format(text))
    if not 2000 <= year <= 2100:
        fail("--valid-thru year looks wrong. Got: {}".format(text))
    return parsed


def main():
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("--"):
        fail("First argument must be an employee ID, for example E001.")

    employee_id = argv[0].strip().upper()

    roster = {row["employee_id"]: row for row in state.load_roster()}
    person = roster.get(employee_id)
    if person is None:
        fail("{} is not on the roster. Check the ID on the worklist.".format(employee_id))

    outcome = (take_option(argv, "--outcome", state.OUTCOME_VERIFIED) or "").strip().lower()
    if outcome not in state.OUTCOMES:
        fail("--outcome must be one of: {}".format(", ".join(state.OUTCOMES)))

    verified_by = (take_option(argv, "--by") or "").strip()
    if not verified_by:
        fail("--by is required. The ledger has to name who performed the lookup.")

    verified_on_raw = take_option(argv, "--on")
    if verified_on_raw:
        try:
            verified_on = state.parse_iso(verified_on_raw)
        except ValueError:
            fail("--on must look like YYYY-MM-DD. Got: {}".format(verified_on_raw))
    else:
        verified_on = date.today()

    if verified_on > date.today():
        fail("--on cannot be in the future.")

    valid_thru = (take_option(argv, "--valid-thru", "") or "").strip()
    credentials = (take_option(argv, "--credentials", "") or "").strip()

    if outcome == state.OUTCOME_VERIFIED:
        if not valid_thru:
            fail("--valid-thru is required when the outcome is 'verified'.")
        expiry = validate_valid_thru(valid_thru)
        if expiry < verified_on:
            print("NOTE: this credential is already expired as of the lookup date.")
    elif valid_thru:
        fail("--valid-thru only applies to a 'verified' outcome.")

    row = {
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "employee_id": employee_id,
        "last_name": person["last_name"],
        "first_name": person["first_name"],
        "outcome": outcome,
        "credentials": credentials,
        "valid_thru": valid_thru,
        "verified_on": "{:%Y-%m-%d}".format(verified_on),
        "verified_by": verified_by,
        "source": (take_option(argv, "--source", DEFAULT_SOURCE) or "").strip(),
        "notes": (take_option(argv, "--notes", "") or "").strip(),
    }

    new_file = not state.LEDGER.exists()
    with open(state.LEDGER, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=state.LEDGER_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)

    name = "{} {}".format(person["first_name"], person["last_name"])
    print("Recorded: {} ({})".format(name, employee_id))
    print("  Outcome:    {}".format(outcome))
    if valid_thru:
        print("  Valid thru: {}".format(valid_thru))
    if credentials:
        print("  Credentials:{}".format(" " + credentials))
    print("  Verified:   {:%m/%d/%Y} by {}".format(verified_on, verified_by))
    print("  Source:     {}".format(row["source"]))

    if outcome != state.OUTCOME_VERIFIED:
        print("\n{} stays on the worklist until a 'verified' result is recorded.".format(name))


if __name__ == "__main__":
    main()
