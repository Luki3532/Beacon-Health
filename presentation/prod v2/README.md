# Credential Tracking — Oracle Fusion HCM themed admin console

A visual mockup of how the credential tracker would look if it were built
inside Beacon's Oracle Fusion Cloud HCM suite, rather than as a separate
website. The point is to show the work landing somewhere staff already log
into, instead of adding one more system to remember.

## Open it

Double-click `index.html`. That is the whole process — no server, no install,
no build step. The data is baked into `assets/data.js` as a plain JavaScript
constant, because browsers block `fetch()` on `file://` URLs.

## What's in it

| Screen | What it shows |
| --- | --- |
| Homepage | Fusion-style tiles with live counts in an Oracle-themed shell |
| Credential Summary | KPIs, everything lapsed or expiring, screening flags |
| ARRT Certification & Registration | Homepage status tile; displays no API data until a feed is available |
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
```

It reads the same files the real scripts use:

- `v_1/employee_data.csv`, `roster.csv`, `managers.csv` — the roster
- `v_5/verification_log.csv` — who verified what, and when
- `v_6/output/FINDINGS_SUMMARY.txt` — exclusion screening flags

Expiration-date logic is ported from `v_5/credential_state.py`. Prod v2 also
filters synthetic fields before calculating status; the command-line tools
may still include those demo records.

Prod v2 withholds fields marked `SYNTHETIC` in the employee source: credentials,
expiration, CE, CQR, and address. These employees remain in the roster, but have
no credential data and do not contribute to current/expiring/lapsed counts.
Other imported records show their recorded provenance; an `ARRT DIRECTORY` or
`ARRT PROFILE` label is not proof of a completed verification. Profile and
screening views separately show whether a named manual lookup is on record.
Date-based status is not live ARRT verification.

## Two things worth knowing

**The names are real.** This mockup renders actual employees from the
credentialing list inside a UI that looks like a production HR system. Treat it
as private operational data and share accordingly.

**Manual verification saves through the local server.** Open the ARRT tile,
find the employee in the manual worklist, and click **Record**. The form guides
the human lookup; it never drives ARRT's access check. Save appends the named
lookup to `v_5/verification_log.csv` and rebuilds the dashboard. A successful
record supplies credential/expiration fields without exposing synthetic
addresses or CE/CQR. Static previews cannot save and display an explicit error.

The `FUSION HCM` tag in the banner is a non-production environment indicator,
matching how this themed demo is positioned.

## ARRT sanctioned-list web updates

With ARRT permission for automated retrieval, start the local updater from the
repository root:

```powershell
python "presentation/prod v2/server.py"
```

Open `http://127.0.0.1:8765`, then use **Data Sources → ARRT - Disciplinary
Sanctioned List → Auto update database from web**. The button retrieves ARRT's
web table, screens employees locally, and regenerates the dashboard. It updates
the local screening summary and `assets/data.js`, not an Oracle database.
No employee data is sent to ARRT. Only matching evidence and update metadata
are stored; the full sanctioned list is not copied to disk.

Incomplete or failed retrievals show an error and retain the previous data.
The server binds only to `127.0.0.1` and accepts updates only from its own
console. File previews and VS Code Live Preview do not run the backend; the
button explains how to open the updater when used there.

This action updates **sanctions screening only**. The separate **ARRT
Certification & Registration** tile remains **Awaiting API**. A sanctioned-list
name match is a lead for review, not proof of identity or credential status.

## Demo manager and immediate email

`demo_roster.json` adds Lucas Carpenter and two clearly labeled fictional
compliance scenarios without modifying the real roster:

- Jimmy John expires **2026-10-29** (25 days from 2026-10-04).
- Wendy King expires **2026-12-03** (60 days from 2026-10-04; enters the
  30-day warning window on 2026-11-03).

The dates persist, so days remaining decrease as time passes. These records
participate in demo status counts but cannot be saved as real ARRT evidence.
Identity lookup candidates and sanctions evidence are shown separately in
Summary; they do not establish current certification or registration.

**Notify all immediately** at the bottom of Summary requires confirmation.
It recalculates expiration against today's date and sends one warning per
authorized manager with lapsed/expiring reports. Wendy is not included until
she enters the warning window. Notifications use TLS-enabled SMTP; no draft or
simulated email is reported as sent. SMTP acceptance does not prove inbox delivery.

Configure these environment variables in the shell **before starting the
server**, then restart it. Do not put credentials in source or send them in chat:

- `BEACON_SMTP_HOST`
- `BEACON_SMTP_PORT` (defaults to 587 for STARTTLS or 465 for SSL)
- `BEACON_SMTP_SECURITY` (`starttls`, default, or `ssl`)
- `BEACON_SMTP_FROM` (one sender email address)
- `BEACON_SMTP_USER` and `BEACON_SMTP_PASSWORD` if authentication is required
- `BEACON_SMTP_ALLOWED_RECIPIENTS` (comma-separated addresses; defaults to
  `Lucasecarpenter@gmail.com` only)

For Gmail use `smtp.gmail.com`, port 587, STARTTLS, your Gmail sender/account,
and an app password where Google permits it. Ordinary account passwords should
not be used. You can instead run the secure prompt launcher from the repository root:

```powershell
& ".\presentation\prod v2\start_with_email.ps1"
```

It prompts for a sender and a hidden app password, then starts the email-enabled
console at `http://127.0.0.1:8766` without conflicting with the existing server.
Use that address to send. Pass `-PythonExecutable "C:\path\to\python.exe"` if
Python is not on PATH. The launcher sets credentials only in the current
process and child server, restores prior environment values when it exits,
and never writes the password to disk.

Managers without an authorized recipient address are explicitly
reported as skipped. Sending is manual, not scheduled, and pressing the button
again intentionally sends another warning. Outcomes are recorded locally in
the ignored `notification_log.jsonl`.
