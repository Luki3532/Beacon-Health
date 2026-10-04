"""Download the OIG LEIE exclusion database.

The LEIE (List of Excluded Individuals/Entities) is published by the HHS Office
of Inspector General as a full CSV, replaced monthly. Public download, no key,
no rate limit, intended for exactly this use: screening a workforce locally.

    https://oig.hhs.gov/exclusions/leie-database-supplement-downloads/

Usage:
    python download_leie.py          # skip if the local copy is < 30 days old
    python download_leie.py --force  # download regardless
"""

import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
HERE = Path(__file__).parent
TARGET = HERE / "leie.csv"
STAMP = HERE / "leie_downloaded.txt"
MAX_AGE_DAYS = 30


def local_age_days() -> int | None:
    if not TARGET.exists() or not STAMP.exists():
        return None
    try:
        when = datetime.strptime(STAMP.read_text(encoding="utf-8").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return (date.today() - when).days


def main() -> None:
    force = "--force" in sys.argv
    age = local_age_days()
    if age is not None and age < MAX_AGE_DAYS and not force:
        print(f"Local copy is {age} days old; skipping download. Use --force to override.")
        return

    print(f"Downloading {LEIE_URL}")
    request = urllib.request.Request(
        LEIE_URL, headers={"User-Agent": "Beacon-credential-tracker/1.0"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - fixed https URL
        data = response.read()

    TARGET.write_bytes(data)
    STAMP.write_text(date.today().strftime("%Y-%m-%d"), encoding="utf-8")

    line_count = data.count(b"\n")
    print(f"Saved {TARGET.name}: {len(data):,} bytes, about {line_count:,} rows")


if __name__ == "__main__":
    main()
