# Presentation — Beacon Credential Tracking

**`prod v2` is the final version.** Present, run, and extend that folder. The
other folders are earlier or alternate builds kept for reference.

## Which folder is which

| Folder | Role | Theme | Status |
| --- | --- | --- | --- |
| [`prod v2/`](./prod%20v2) | **Final version** | Oracle Fusion HCM | Use this one |
| [`prod/`](./prod) | Earlier build | PeopleSoft | Superseded |
| [`prod v3/`](./prod%20v3) | Alternate build (empty cold-start data) | PeopleSoft | Not finished; not used for the demo |
| [`slides/`](./slides) | Slide decks | — | See the note below |

## Why prod v2 is final

It is the only build that includes everything below.

- **Honest data provenance.** Synthetic credential fields are withheld, so no
  fabricated ARRT status is shown as fact. Each record shows its source, and an
  employee with no verified source reads "Never Verified".
- **ARRT certification & registration tile.** Shows **Awaiting API**, because
  no ARRT feed exists yet.
- **ARRT disciplinary sanctioned list updater.** The *Auto update database from
  web* button retrieves ARRT's list, screens employees locally, and refreshes
  the dashboard. It updates local files, not an Oracle database.
- **Manual verification workflow.** A searchable ARRT worklist with a *Record*
  link opens a guided form. Saving appends a named entry to the verification
  ledger. A person completes ARRT's lookup; the app never automates its
  CAPTCHA.
- **Separate evidence in Summary.** NPPES identity candidates, sanctions
  screening, and credential status are shown separately, and none is presented
  as proof of the others.
- **Manager demo scenario.** Lucas Carpenter with two fictional employees:
  Jimmy John (expires 2026-10-29, 25 days) and Wendy King (expires 2026-12-03,
  60 days). Both are labeled `[DEMO]`.
- **Immediate email warnings.** *Notify all immediately* at the bottom of
  Summary sends real SMTP email once the server is configured. See below.
- **API design.** [`BACON_API.md`](./prod%20v2/BACON_API.md) is a fictional
  reference for how this back end could become a real API.

## Run the final version

Quick view (no backend), double-click `prod v2/index.html`.

Full console with the sanctions updater, verification saving, and email:

```powershell
python "presentation/prod v2/server.py"
```

Then open `http://127.0.0.1:8765`.

To send email, use the secure launcher. It prompts for a Gmail address and app
password and never writes the password to disk:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\presentation\prod v2\start_with_email.ps1"
```

Open `http://127.0.0.1:8766`, go to Summary, and use *Notify all immediately*.
Email is only reported as sent after the SMTP server accepts it. SMTP acceptance
does not guarantee inbox delivery.

Tests, from `prod v2/`:

```powershell
python -B -m unittest test_profile_source test_arrt_update test_manual_email -v
```

Full details are in [`prod v2/README.md`](./prod%20v2/README.md).

## What is real and what is not

- **Real:** the roster and verification ledger, the ARRT sanctioned-list
  retrieval and local name screening, and the cached NPPES lookups. A name match
  is a lead for review, not proof of identity.
- **Demo only:** Lucas Carpenter's two employees, and `BACON_API.md`. Every
  host, ID, and number in the API document is invented.
- **Not available:** live ARRT registration status. This needs a data feed
  arranged directly with ARRT. Until then, verification is a recorded human
  lookup.
- **Private data:** the roster contains real employee names. Share the
  generated `assets/data.js` carefully; it is excluded from Git.

## Known gaps

- `slides/Beacon_Credential_Tracking_Briefing.html` was built from an earlier
  snapshot, before synthetic credential data was withheld. Its credential counts
  are out of date and should be regenerated before presenting.
- `prod/` and `prod v3/` still use the earlier PeopleSoft theme and do not
  include the changes above.
