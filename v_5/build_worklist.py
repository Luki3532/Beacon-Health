"""Build the verification worklist: who needs a credential lookup right now.

Reads the verification ledger and prints only the people who need attention.
Everyone verified and not expiring soon is left out, which is the point --
after the first pass this list is short.

Usage:
    python build_worklist.py
    python build_worklist.py --as-of 2026-10-03   # pretend today is this date
    python build_worklist.py --window 45          # widen the alert window
    python build_worklist.py --all                # include people already current
"""

import csv
import sys
from datetime import date, datetime

import credential_state as state

WORKLIST_TXT = state.HERE / "worklist.txt"
WORKLIST_CSV = state.HERE / "worklist.csv"

ARRT_LOOKUP_URL = "https://www.arrt.org/"


def parse_args(argv):
    today = date.today()
    window = state.WINDOW_DAYS
    include_current = "--all" in argv

    if "--as-of" in argv:
        raw = argv[argv.index("--as-of") + 1]
        today = datetime.strptime(raw, "%Y-%m-%d").date()
    if "--window" in argv:
        window = int(argv[argv.index("--window") + 1])

    return today, window, include_current


def record_card(row, position, total):
    """The block a person works from when doing one lookup."""
    on_file = row["on_file"] or {}
    hint = on_file.get("valid_thru", "")
    credentials = on_file.get("credentials", "")

    lines = [
        "[{} of {}]  {}  ({})".format(
            position, total, state.full_name(row), row["employee_id"]
        ),
        "    Status:    {}".format(state.describe(row)),
        "    Manager:   {}".format(state.manager_display(row["manager"])),
    ]

    attempt = row.get("last_attempt")
    if attempt:
        lines.append(
            "    Last check: {} by {} - {} ({})".format(
                attempt["verified_on"],
                attempt["verified_by"],
                attempt["outcome"],
                attempt["source"],
            )
        )
        if attempt.get("notes"):
            lines.append("    Note:      {}".format(attempt["notes"]))
    else:
        lines.append("    Last check: none on record")

    if hint:
        lines.append(
            "    On file:   {} valid thru {}  (UNVERIFIED - synthetic placeholder)".format(
                credentials or "credentials unknown", hint
            )
        )

    lines += [
        "    Look up:   {} {} at {}".format(
            row["first_name"], row["last_name"], ARRT_LOOKUP_URL
        ),
        "    Record it: python record_verification.py {} --valid-thru MM/YYYY "
        '--credentials "R.T.(R)(ARRT)" --by "Your Name"'.format(row["employee_id"]),
        "",
    ]
    return lines


def main():
    today, window, include_current = parse_args(sys.argv[1:])

    everyone = state.build_state(today=today, window_days=window)
    if include_current:
        worklist = everyone
    else:
        worklist = [row for row in everyone if row["status"] != state.CURRENT]

    counts = {}
    for row in everyone:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    header = [
        "CREDENTIAL VERIFICATION WORKLIST",
        "=" * 72,
        "As-of date:  {:%m/%d/%Y}".format(today),
        "Window:      {} days".format(window),
        "Roster:      {} people".format(len(everyone)),
        "",
        "  Lapsed:          {}".format(counts.get(state.LAPSED, 0)),
        "  Due in window:   {}".format(counts.get(state.DUE, 0)),
        "  Never verified:  {}".format(counts.get(state.NEVER_VERIFIED, 0)),
        "  Current:         {}".format(counts.get(state.CURRENT, 0)),
        "",
        "Needing attention: {}".format(len(worklist)),
        "=" * 72,
        "",
    ]

    if not worklist:
        body = [
            "Nothing to verify today.",
            "",
            "Every credential on the roster has been verified by a person and",
            "none expires within the next {} days.".format(window),
        ]
    else:
        body = [
            "Each entry below needs a human lookup. Verify the registration,",
            "then record the result with the command shown.",
            "",
            "-" * 72,
            "",
        ]
        for position, row in enumerate(worklist, start=1):
            body += record_card(row, position, len(worklist))

    footer = [
        "-" * 72,
        "No date becomes 'verified' until a named person records it.",
        "Contains real employee names - keep local, do not share or commit.",
    ]

    WORKLIST_TXT.write_text("\n".join(header + body + footer), encoding="utf-8")

    with open(WORKLIST_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["employee_id", "last_name", "first_name", "manager", "status",
             "valid_thru", "days_remaining"]
        )
        for row in worklist:
            writer.writerow([
                row["employee_id"],
                row["last_name"],
                row["first_name"],
                row["manager"],
                row["status"],
                "{:%m/%Y}".format(row["expiry"]) if row["expiry"] else "",
                row["days"] if row["days"] is not None else "",
            ])

    print("\n".join(header))
    for row in worklist[:10]:
        print("  {:<6} {:<28} {}".format(
            row["employee_id"], state.full_name(row), state.describe(row)
        ))
    if len(worklist) > 10:
        print("  ... and {} more".format(len(worklist) - 10))

    print("\nWrote {}".format(WORKLIST_TXT.name))
    print("Wrote {}".format(WORKLIST_CSV.name))


if __name__ == "__main__":
    main()
