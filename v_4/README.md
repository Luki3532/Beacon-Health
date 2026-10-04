# v_4 — Two-source exclusion and sanction screening

Searches every person on the credentialing list against **two** public
databases, one person at a time, and writes a separate `.txt` result file for
each person.

## Why a second source

MDHHS says it plainly on its own sanctioned provider page: its list is built
partly from outside sources, so "there may be instances of providers not
appearing on the list," and it directs readers to also monitor the federal
lists. The reverse is also true — a state Medicaid termination does not always
produce a federal exclusion. Neither list is complete alone, which is why
screening against both is standard practice.

## Sources

| Source | Scope | Format | Refresh |
| --- | --- | --- | --- |
| OIG LEIE | Federal (all federal health care programs) | CSV download | Monthly |
| MDHHS Sanctioned Provider List | Michigan Medicaid | XLSX download | As changes are published |

Neither agency offers a public API. OIG states outright that there are no
plans for one and directs bulk users to the downloadable file. MDHHS publishes
only the spreadsheet and a PDF. Both scripts use the agencies' own intended
bulk-distribution channel — no scraping, no form automation, no CAPTCHA.

## Files

| File | Purpose |
| --- | --- |
| `download_mi_sanctions.py` | Downloads the MDHHS spreadsheet; skips if the local copy is under a week old |
| `xlsx_reader.py` | Minimal `.xlsx` parser built on the standard library, so there are no dependencies |
| `lookup_each.py` | Per-person search across both databases; writes one file per person |
| `verify_mi_index.py` | Sanity check that the Michigan index matches names known to be on the list |
| `results/` | One `.txt` per person |
| `lookup_index.txt` | Summary of every person with their match counts |

## Running it

```powershell
$py = "C:\Users\Lucas\AppData\Roaming\uv\python\cpython-3.14-windows-x86_64-none\python.exe"

# Refresh the source data
& $py ..\v_2\download_leie.py
& $py download_mi_sanctions.py

# Confirm the Michigan parser still works after a refresh
& $py verify_mi_index.py

# Screen everyone
& $py lookup_each.py
& $py lookup_each.py --limit 5    # smoke test
```

Run `verify_mi_index.py` after every download. MDHHS can change the
spreadsheet's layout without notice, and a layout change would silently turn
every result into a false "CLEAR."

## Reading the results

`CLEAR` on both sources is the expected outcome for a compliant workforce. A
run where nobody is flagged is the screening working, not failing —
`verify_mi_index.py` is what proves the search is live.

A name match is **not** proof of exclusion. Neither public file contains SSNs,
so identity cannot be confirmed from either one. Every hit must be confirmed
with the issuing agency:

- Federal: <https://exclusions.oig.hhs.gov/>
- Michigan: MDHHS-SanctionProviderList@michigan.gov

Expect false positives on common names. Compare specialty, city, state, and
NPI before escalating anything.

## What this does not cover

Exclusion screening is not credential verification. It answers "is this person
barred from federal or Michigan Medicaid programs," not "is this person's ARRT
registration current." ARRT expiration dates remain unavailable through any
automated channel and still require an authorized arrangement with ARRT.

## Data handling

`results/` pairs real employee names with federal and state sanction records.
Keep it local. Do not commit it or share it.
