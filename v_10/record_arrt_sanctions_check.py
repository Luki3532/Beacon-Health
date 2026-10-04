"""
v_10 - Record a manual ARRT disciplinary sanctioned-list check.

A person searches the public list at https://www.arrt.org/sanctioned-list
(search tips: last name, first name, or "last, first"), then records what they
saw here. Entries are append-only: a correction is a new row, never an edit.

Usage:
    python record_arrt_sanctions_check.py --pending
    python record_arrt_sanctions_check.py E001 --result clear --by "Your Name"
    python record_arrt_sanctions_check.py E001 --result match --by "Your Name" \
        --sanction Revoke --sanction-date 02/2006 --arrt-id 176964 \
        --notes "City/state differ - confirm with ARRT 651.687.0048"
    python record_arrt_sanctions_check.py E001 --result unclear --by "Your Name" \
        --notes "Two people with the same name, need ARRT to disambiguate"

Results:
    clear    searched, no matching person on the list
    match    a person on the list is the employee (identity confirmed)
    unclear  a same-name entry exists but identity is not confirmed

A name match is a LEAD, not proof. ARRT does not publish SSN or full birth date.
"""

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EMPLOYEE_DATA = ROOT / "v_1" / "employee_data.csv"
LOG = HERE / "arrt_sanctions_checks.csv"

FIELDS = [
    "logged_at", "employee_id", "name", "result", "checked_on", "checked_by",
    "sanction", "sanction_date", "arrt_id", "notes",
]
RESULTS = ("clear", "match", "unclear")


def read_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def latest_by_employee():
    latest = {}
    for row in read_csv(LOG):
        latest[row["employee_id"]] = row
    return latest


def show_pending():
    people = read_csv(EMPLOYEE_DATA)
    done = latest_by_employee()
    pending = [p for p in people if p["employee_id"] not in done]
    print("{} of {} employees have a recorded ARRT sanctions check; {} pending."
          .format(len(done), len(people), len(pending)))
    for p in pending:
        print("  {}  {}, {}".format(p["employee_id"], p["last_name"], p["first_name"]))


def record(args):
    people = {p["employee_id"]: p for p in read_csv(EMPLOYEE_DATA)}
    person = people.get(args.employee_id)
    if person is None:
        raise SystemExit("Unknown employee id: {}".format(args.employee_id))
    if not args.by.strip():
        raise SystemExit("--by is required: a check with no named person is not evidence.")
    if args.result == "match" and not (args.sanction or args.notes):
        raise SystemExit("A match needs --sanction and/or --notes describing what was found.")

    new_file = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "logged_at": datetime.now().isoformat(timespec="seconds"),
            "employee_id": args.employee_id,
            "name": "{} {}".format(person["first_name"], person["last_name"]),
            "result": args.result,
            "checked_on": args.on or date.today().isoformat(),
            "checked_by": args.by.strip(),
            "sanction": args.sanction,
            "sanction_date": args.sanction_date,
            "arrt_id": args.arrt_id,
            "notes": args.notes,
        })
    print("Recorded {} for {} {} ({}).".format(
        args.result, person["first_name"], person["last_name"], args.employee_id))
    print("Regenerate the console: python \"presentation/prod v2/build_data.py\"")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("employee_id", nargs="?")
    parser.add_argument("--pending", action="store_true",
                        help="list employees with no recorded check")
    parser.add_argument("--result", choices=RESULTS)
    parser.add_argument("--by", default="")
    parser.add_argument("--on", help="date checked (YYYY-MM-DD); default today")
    parser.add_argument("--sanction", default="")
    parser.add_argument("--sanction-date", default="")
    parser.add_argument("--arrt-id", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    if args.pending:
        show_pending()
        return
    if not args.employee_id or not args.result:
        parser.error("employee_id and --result are required (or use --pending)")
    record(args)


if __name__ == "__main__":
    sys.exit(main())
