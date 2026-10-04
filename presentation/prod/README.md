# Credential Tracking — PeopleSoft-style admin console

A visual mockup of how the credential tracker would look if it were built
inside Beacon's existing PeopleSoft HCM system, rather than as a separate
website. The point is to show the work landing somewhere staff already log
into, instead of adding one more system to remember.

## Open it

Double-click `index.html`. That is the whole process — no server, no install,
no build step. The data is baked into `assets/data.js` as a plain JavaScript
constant, because browsers block `fetch()` on `file://` URLs.

## What's in it

| Screen | What it shows |
| --- | --- |
| Homepage | Fluid tiles with live counts, the way PeopleSoft 9.2 opens |
| Credential Summary | KPIs, everything lapsed or expiring, screening flags |
| Manager Worklist | Rolled up by manager, then drill into one manager |
| Employee Detail | ARRT registration, screening results, verification history |
| Verification Entry | The form Teresa would fill in after an ARRT lookup |
| Audit Log | Every lookup on record, including the ones that found nothing |

Navigation is real: tiles, breadcrumbs, the back arrow, sortable grid columns,
paging, and search all work. The notification bell shows lapsed + expiring.

## Regenerating the data

```
python build_data.py
python build_data.py --as-of 2026-10-03     # pin the date
python build_data.py --fictional            # swap in pseudonyms
```

It reads the same files the real scripts use:

- `v_1/employee_data.csv`, `roster.csv`, `managers.csv` — the roster
- `v_5/verification_log.csv` — who verified what, and when
- `v_6/output/FINDINGS_SUMMARY.txt` — exclusion screening flags

Status logic is ported from `v_5/credential_state.py`, so the console and the
command-line tools always agree on who is lapsed, due, and current.

## Two things worth knowing

**The names are real.** This mockup renders actual employees from the
credentialing list inside a UI that looks like a production HR system. That is
fine for a private walkthrough and a bad idea for a shared screen, a slide
deck, or anything that leaves your machine. `--fictional` swaps in invented
names while keeping every count, date, and status identical, so the demo looks
exactly the same and tells you nothing about a real person. When in doubt, use
it.

**Nothing saves.** The Verification Entry form validates input and then tells
you plainly that it did not write anything, along with the real
`record_verification.py` command that would. A mockup that said "Saved" would
be teaching people to trust a screen that quietly loses their work.

The `HR92DMO` tag in the banner is PeopleSoft's own non-production database
indicator — the same signal a real demo instance displays.
