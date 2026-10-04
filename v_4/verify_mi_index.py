"""Sanity check: confirm the Michigan index actually matches.

Takes a few real names straight out of the MDHHS spreadsheet and searches for
them. If these do not come back as matches, the index or the parser is broken
and every "CLEAR" result is meaningless.

Usage:
    python verify_mi_index.py
"""

from lookup_each import load_mi_index, search_index

index, total = load_mi_index()
print("Indexed {:,} sanctioned individuals, {:,} distinct names.\n".format(total, len(index)))

# Pull real sample names out of the index itself so this never goes stale.
samples = sorted(index.keys())[:3] + sorted(index.keys())[-3:]

failures = 0
for last, first in samples:
    matches = search_index(index, last, first)
    status = "OK  " if matches else "FAIL"
    if not matches:
        failures += 1
    print("{}  {:<20} {:<20} -> {} record(s)".format(status, first, last, len(matches)))

print("\nControl (a name that should not be on the list):")
control = search_index(index, "Zzzzqqqx", "Nobody")
print("  {} -> {} record(s)".format("OK  " if not control else "FAIL", len(control)))
if control:
    failures += 1

print("\n{} failure(s).".format(failures))
raise SystemExit(1 if failures else 0)
