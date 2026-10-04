"""
Download the Michigan Medicaid Sanctioned Provider List.

Source page:
  https://www.michigan.gov/mdhhs/doing-business/providers/providers/
  billingreimbursement/list-of-sanctioned-providers

MDHHS publishes the list as an .xlsx file. There is no API. MDHHS updates the
list as additions and deletions are made, so we re-download on a cadence.

Usage:
  python download_mi_sanctions.py
  python download_mi_sanctions.py --force
"""

import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

MI_URL = (
    "https://www.michigan.gov/mdhhs/-/media/Project/Websites/mdhhs/"
    "Assistance-Programs/Medicaid-BPHASA/MI-Sanctioned-Provider-List/"
    "MI_Sanctioned_Provider_List-XLSX.xlsx"
)

XLSX_PATH = HERE / "mi_sanctions.xlsx"
STAMP_PATH = HERE / "mi_sanctions_downloaded.txt"

# MDHHS updates irregularly. Weekly is a safe refresh cadence.
MAX_AGE_DAYS = 7


def read_stamp():
    if not STAMP_PATH.exists():
        return None
    try:
        return datetime.fromisoformat(STAMP_PATH.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def is_fresh():
    if not XLSX_PATH.exists():
        return False
    stamp = read_stamp()
    if stamp is None:
        return False
    return datetime.now() - stamp < timedelta(days=MAX_AGE_DAYS)


def download():
    print("Downloading Michigan Medicaid Sanctioned Provider List...")
    print("  " + MI_URL)

    request = urllib.request.Request(
        MI_URL,
        headers={"User-Agent": "Beacon-Credentialing-Tool/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()

    if not data.startswith(b"PK"):
        print("ERROR: response was not an .xlsx file. The MDHHS link may have moved.")
        print("Check the source page and update MI_URL.")
        return False

    XLSX_PATH.write_bytes(data)
    STAMP_PATH.write_text(datetime.now().isoformat(), encoding="utf-8")

    print("Saved {} ({:,} bytes)".format(XLSX_PATH.name, len(data)))
    return True


def main():
    force = "--force" in sys.argv

    if is_fresh() and not force:
        stamp = read_stamp()
        print("Local copy is current (downloaded {}).".format(stamp.strftime("%Y-%m-%d")))
        print("Use --force to download anyway.")
        return 0

    return 0 if download() else 1


if __name__ == "__main__":
    raise SystemExit(main())
