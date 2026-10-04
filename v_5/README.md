# v_5 — Verification worklist and audit ledger

Answers "who needs a credential lookup today" and keeps a permanent record of
who verified what, when.

This is the piece that addresses what Teresa actually described: not the
lookup itself, but the tracking, remembering, and chasing around it.

## The idea

A credential counts as verified only because a named person looked it up and
recorded the result. Nothing here contacts ARRT.

The payoff is that verification is self-renewing. Verify someone once and the
tool goes quiet on them until 30 days before their date, then surfaces them
automatically. The full-roster pass happens once, at bootstrap. After that the
tool tells you who to look at instead of you having to remember.

Expiration dates spread across the calendar by each person's own date, so the
steady state is roughly **8 people a month** — about ten minutes of work, but
only if something remembers who those eight are.

## Statuses

| Status | Meaning | On the worklist |
| --- | --- | --- |
| `NEVER_VERIFIED` | No successful verification on record | Yes |
| `LAPSED` | Verified date is in the past | Yes, listed first |
| `DUE` | Expires within the window (default 30 days) | Yes |
| `CURRENT` | Verified, not expiring soon | No |

Anything not verified is due. That makes the cold start fall out of the same
rule rather than needing special handling.

## Files

| File | Purpose |
| --- | --- |
| `credential_state.py` | Reads the ledger, computes each person's status |
| `build_worklist.py` | Writes the worklist of people needing a lookup |
| `record_verification.py` | Appends one verification result to the ledger |
| `credential_source.py` | Boundary for an authorized feed — currently refuses by design |
| `verification_log.csv` | Append-only audit ledger |
| `worklist.txt` | Record cards for each person needing a lookup |
| `worklist.csv` | Same list, machine-readable |

## Running it

```powershell
$py = "C:\Users\Lucas\AppData\Roaming\uv\python\cpython-3.14-windows-x86_64-none\python.exe"
cd v_5

& $py build_worklist.py                      # who needs a lookup
& $py build_worklist.py --as-of 2026-11-15   # pretend today is this date
& $py build_worklist.py --window 45          # widen the window
& $py build_worklist.py --all                # include people already current
```

Record a result after each lookup:

```powershell
& $py record_verification.py E001 --valid-thru 10/2027 `
    --credentials "R.T.(R)(ARRT)" --by "Your Name"

& $py record_verification.py E022 --outcome not-found --by "Your Name" `
    --notes "No record returned; following up with technologist"
```

`--outcome` is `verified`, `discrepancy`, or `not-found`. Only `verified`
clears someone from the worklist — the other two are recorded so the same dead
end is not silently re-walked, but the person stays due.

`--by` is required. A verification with no named verifier is not evidence.

## The ledger

Append-only. A correction is a new row, never an edit, so history stays
intact. Later rows win when computing current status.

```
logged_at, employee_id, last_name, first_name, outcome, credentials,
valid_thru, verified_on, verified_by, source, notes
```

This is the audit artifact. It's stronger than the current paper process
because every date carries a named verifier, a timestamp, and the source.

## Demo data

`verification_log.csv` ships with four rows marked
`DEMO DATA - not a real verification`, covering current, due, lapsed, and
not-found. **Delete the file before real use** — it recreates itself on the
first real entry.

Demo rows are deliberately not attributed to any real person. A ledger that
looks like an audit trail but contains fabricated entries under someone's name
is worse than no ledger.

## What this does not do

It does not contact ARRT. `credential_source.py` defines the interface for an
authorized feed and raises until one exists. ARRT has no public API, and their
directory is behind an anti-robot check — evidence obtained by circumventing
that would not hold up in a survey, which defeats the purpose.

If Beacon obtains authorized access, implement `fetch_credential()` and
nothing else in the pipeline changes.

ARRT employer inquiries: **651-687-0048**

## Known gap

A cached date can go stale. If a registration is revoked mid-cycle, the tool
stays silent until the stored date comes around. Date-based alerting cannot
catch mid-cycle revocation.

ARRT publishes a **Disciplinary Sanctioned List** — a public table covering
exactly this. It would slot into the v_4 pattern alongside LEIE and MDHHS.
Their terms for automated access need reading first.

## Data handling

`verification_log.csv`, `worklist.txt`, and `worklist.csv` all contain real
employee names. Keep local. Do not commit or share.

## Relationship to the other versions

| Version | Role |
| --- | --- |
| v_1 | Roster, synthetic data, 30-day alert dry run |
| v_2 | OIG LEIE batch exclusion screening |
| v_3 | Per-person LEIE lookups |
| v_4 | Adds Michigan Medicaid sanctions as a second source |
| v_5 | Verification worklist and audit ledger |

The `valid_thru` dates in `v_1/employee_data.csv` are synthetic. v_5 treats
them as unverified hints only — they appear on record cards labeled as such to
suggest when to expect a renewal, but they never drive status.

Next step would be pointing [v_1/run_alerts.py](../v_1/run_alerts.py) at
`credential_state.py` so manager emails are driven by verified dates rather
than synthetic ones.
