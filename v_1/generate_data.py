"""Build the synthetic v_1 data set as three CSV files.

roster.csv         employee_id, last_name, first_name, manager   (real names/managers from the credentialing list)
employee_data.csv  employee_id + ARRT-style fields               (ALL FABRICATED)
managers.csv       manager, email                                (ALL FABRICATED, example.com addresses)

Re-running overwrites the CSVs with the same output (fixed random seed).
"""

import csv
import random
import re
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE.parent / "credentialing list"
SEED = 20261003

# Manager with no email on file, to exercise the "missing email" check.
MANAGER_WITHOUT_EMAIL = "Hemenway, Bryan A"

CREDENTIAL_SETS = [
    "R.T.(R)(ARRT)",
    "R.T.(R)(CT)(ARRT)",
    "R.T.(R)(M)(ARRT)",
    "R.T.(R)(MR)(ARRT)",
    "R.T.(MR)(ARRT)",
    "R.T.(N)(ARRT)",
    "R.T.(S)(ARRT)",
    "R.T.(T)(ARRT)",
]
DISCIPLINES = {
    "R": "Radiography",
    "CT": "Computed Tomography",
    "M": "Mammography",
    "MR": "Magnetic Resonance Imaging",
    "N": "Nuclear Medicine Technology",
    "S": "Sonography",
    "T": "Radiation Therapy",
}
CITIES = [
    ("Kalamazoo", "49001"),
    ("Portage", "49002"),
    ("Battle Creek", "49015"),
    ("Paw Paw", "49079"),
    ("Plainwell", "49080"),
    ("Mattawan", "49071"),
    ("Vicksburg", "49097"),
    ("Schoolcraft", "49087"),
    ("Otsego", "49078"),
    ("Bloomingdale", "49026"),
]

# Valid Thru as (year, month) for the people not listed in OVERRIDES.
RANDOM_VALID_THRU = [(2026, 12)] + [(2027, m) for m in range(1, 10)]

# Test cases, relative to a reference date of 10/3/2026 (30-day window ends 11/2/2026).
# Each override applies to the first roster row with that name only, so the
# second "Adam Brege" gets a random date.
OVERRIDES = {
    # expiring 10/2026 -> should alert
    ("Adam", "Brege"): (2026, 10),
    ("Glenn", "Eikelboom"): (2026, 10),
    ("Jennifer", "Squires"): (2026, 10),
    ("Courtney", "Waterloo"): (2026, 10),
    ("Emily", "Bigda"): (2026, 10),
    ("Madison", "Brink"): (2026, 10),
    ("Chris", "Hilton"): (2026, 10),  # manager has no email
    # already lapsed 09/2026
    ("Peter", "Sagmoe"): (2026, 9),
    ("Rachel", "Dougherty"): (2026, 9),
    # 11/2026 -> ends 11/30, outside the 30-day window
    ("Meghan", "Wolf"): (2026, 11),
    ("Denise", "Dennis"): (2026, 11),
}
# Guarantee at least one person holds two disciplines.
FORCE_CREDENTIALS = {("Glenn", "Eikelboom"): "R.T.(R)(CT)(ARRT)"}


def normalize_manager(raw: str) -> str:
    last, _, first = raw.partition(",")
    return f"{last.strip()}, {first.strip()}"


def manager_email(manager: str) -> str:
    last, first = [p.strip() for p in manager.split(",", 1)]
    given = re.sub(r"[^a-z]", "", first.split()[0].lower())
    surname = re.sub(r"[^a-z]", "", last.lower())
    return f"{given}.{surname}@example.com"


def read_roster() -> list[dict]:
    rows = []
    with open(SOURCE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # header
        for line in reader:
            if len(line) < 3 or not line[0].strip() or not line[1].strip():
                continue
            rows.append(
                {
                    "first_name": line[0].strip(),
                    "last_name": line[1].strip(),
                    "manager": normalize_manager(line[2]),
                }
            )
    for i, row in enumerate(rows, start=1):
        row["employee_id"] = f"E{i:03d}"
    return rows


def fmt(d: date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def make_employee_data(rng: random.Random, roster: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out = []
    for person in roster:
        key = (person["first_name"], person["last_name"])
        if key in OVERRIDES and key not in seen:
            year, month = OVERRIDES[key]
        else:
            year, month = rng.choice(RANDOM_VALID_THRU)
        credentials = (
            FORCE_CREDENTIALS[key]
            if key in FORCE_CREDENTIALS and key not in seen
            else rng.choice(CREDENTIAL_SETS)
        )
        seen.add(key)

        ce_start = date(year - 2, month, 1)
        ce_end = date(year, month, 1) - timedelta(days=1)
        cqr_start = date(year - 3, month, 1)
        disciplines = [c for c in re.findall(r"\(([A-Z]+)\)", credentials) if c != "ARRT"]
        cqr = "; ".join(
            f"{DISCIPLINES[c]} {fmt(cqr_start)}-{fmt(ce_end)} "
            f"{'Completed' if rng.random() < 0.7 else 'In Progress'}"
            for c in disciplines
        )
        city, zip5 = rng.choice(CITIES)
        out.append(
            {
                "employee_id": person["employee_id"],
                "last_name": person["last_name"],
                "first_name": person["first_name"],
                "city": city,
                "state": "MI",
                "zip": f"{zip5}-{rng.randint(1000, 9999)}",
                "country": "U.S.A.",
                "credentials": credentials,
                "valid_thru": f"{month:02d}/{year}",
                "ce_biennium_start": fmt(ce_start),
                "ce_biennium_end": fmt(ce_end),
                "cqr_periods": cqr,
                "data_source": "SYNTHETIC",
            }
        )
    return out


def write_csv(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(HERE / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {name}: {len(rows)} rows")


def main() -> None:
    rng = random.Random(SEED)
    roster = read_roster()
    employee_data = make_employee_data(rng, roster)

    manager_names = sorted({p["manager"] for p in roster})
    managers = [
        {"manager": m, "email": "" if m == MANAGER_WITHOUT_EMAIL else manager_email(m)}
        for m in manager_names
    ]

    write_csv("roster.csv", ["employee_id", "last_name", "first_name", "manager"], roster)
    write_csv(
        "employee_data.csv",
        [
            "employee_id", "last_name", "first_name", "city", "state", "zip", "country",
            "credentials", "valid_thru", "ce_biennium_start", "ce_biennium_end",
            "cqr_periods", "data_source",
        ],
        employee_data,
    )
    write_csv("managers.csv", ["manager", "email"], managers)


if __name__ == "__main__":
    main()
