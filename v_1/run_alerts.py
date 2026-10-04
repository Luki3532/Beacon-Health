"""Dry-run credential alerts: find ARRT Valid Thru dates within 30 days and
write one email per manager. Nothing is ever sent.

Usage:
    python run_alerts.py                    # uses today's date
    python run_alerts.py --as-of 2026-10-03 # pretend today is this date
"""

import csv
import sys
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
WINDOW_DAYS = 30
OUTPUT = HERE / "alerts_dry_run.txt"


def read_csv(name: str) -> list[dict]:
    with open(HERE / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def valid_thru_date(text: str) -> date:
    """ARRT gives month/year only; treat it as the last day of that month."""
    month, year = (int(p) for p in text.split("/"))
    return date(year, month, monthrange(year, month)[1])


def display_name(manager: str) -> str:
    last, first = [p.strip() for p in manager.split(",", 1)]
    return f"{first} {last}"


def check_data(roster, employee_data, managers) -> list[str]:
    problems = []
    roster_ids = [r["employee_id"] for r in roster]
    data_ids = [d["employee_id"] for d in employee_data]
    for label, ids in (("roster", roster_ids), ("employee_data", data_ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            problems.append(f"Duplicate employee_id in {label}: {sorted(dupes)}")
    for missing in sorted(set(roster_ids) - set(data_ids)):
        problems.append(f"{missing} is on the roster but has no employee data")
    for extra in sorted(set(data_ids) - set(roster_ids)):
        problems.append(f"{extra} has employee data but is not on the roster")
    manager_emails = {m["manager"]: m["email"].strip() for m in managers}
    for manager in sorted({r["manager"] for r in roster}):
        if manager not in manager_emails:
            problems.append(f"Manager '{manager}' is not in managers.csv")
        elif not manager_emails[manager]:
            problems.append(f"Manager '{manager}' has no email on file")
    return problems


def build_email(manager: str, email: str, expiring: list, lapsed: list) -> str:
    total = len(expiring) + len(lapsed)
    lines = [
        f"To: {email}",
        f"Subject: ARRT credential alert: {total} to review",
        "",
        f"Hello {display_name(manager)},",
        "",
    ]

    def table(items):
        for name, creds, expiry, days in items:
            note = f"{days} days left" if days >= 0 else f"lapsed {-days} days ago"
            lines.append(f"  - {name}  {creds}  valid thru {expiry:%m/%d/%Y}  ({note})")
        lines.append("")

    if expiring:
        lines.append(f"These credentials expire within {WINDOW_DAYS} days:")
        table(expiring)
    if lapsed:
        lines.append("These credentials have already lapsed:")
        table(lapsed)
    lines.append("Please confirm each renewal with the technologist.")
    return "\n".join(lines)


def main() -> None:
    today = date.today()
    if len(sys.argv) == 3 and sys.argv[1] == "--as-of":
        today = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()

    roster = read_csv("roster.csv")
    employee_data = read_csv("employee_data.csv")
    managers = read_csv("managers.csv")

    problems = check_data(roster, employee_data, managers)
    emails = {m["manager"]: m["email"].strip() for m in managers}
    data_by_id = {d["employee_id"]: d for d in employee_data}

    expiring = defaultdict(list)
    lapsed = defaultdict(list)
    for person in roster:
        data = data_by_id.get(person["employee_id"])
        if data is None:
            continue
        expiry = valid_thru_date(data["valid_thru"])
        days = (expiry - today).days
        item = (
            f"{person['first_name']} {person['last_name']} ({person['employee_id']})",
            data["credentials"],
            expiry,
            days,
        )
        if days < 0:
            lapsed[person["manager"]].append(item)
        elif days <= WINDOW_DAYS:
            expiring[person["manager"]].append(item)

    out = [
        "DRY RUN - SYNTHETIC TEST DATA - NO EMAIL WAS SENT",
        f"As-of date: {today:%m/%d/%Y}    Window: {WINDOW_DAYS} days",
        "",
    ]
    for manager in sorted(set(expiring) | set(lapsed)):
        exp = sorted(expiring[manager], key=lambda i: i[2])
        lap = sorted(lapsed[manager], key=lambda i: i[2])
        email = emails.get(manager, "")
        out.append("=" * 70)
        if not email:
            out.append(f"NOT SENT - no email on file for {manager}")
            out.append(f"  would have listed {len(exp)} expiring, {len(lap)} lapsed")
            for name, creds, expiry, days in exp + lap:
                out.append(f"  - {name}  {creds}  valid thru {expiry:%m/%d/%Y}")
        else:
            out.append(build_email(manager, email, exp, lap))
        out.append("")

    out.append("=" * 70)
    out.append("Data checks:")
    if problems:
        out.extend(f"  - {p}" for p in problems)
    else:
        out.append("  all passed")

    text = "\n".join(out)
    OUTPUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {OUTPUT}")


if __name__ == "__main__":
    main()
