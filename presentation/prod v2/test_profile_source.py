import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import build_data


class ProfileSourceTests(unittest.TestCase):
    def test_synthetic_profile_is_withheld(self):
        record = {
            "data_source": "SYNTHETIC", "credentials": "R.T.(N)(ARRT)",
            "valid_thru": "10/2026", "city": "Example",
            "ce_biennium_start": "10/1/2024", "cqr_periods": "Completed",
        }
        safe = build_data.profile_data(record)
        self.assertEqual(safe, {"data_source": "SYNTHETIC"})
        self.assertEqual(build_data.status_for(safe.get("valid_thru", ""), date(2026, 10, 4)),
                         ("NEVER_VERIFIED", None))
        self.assertEqual(record["valid_thru"], "10/2026")

    def test_imported_profile_is_preserved(self):
        record = {"data_source": "ARRT PROFILE", "valid_thru": "03/2027"}
        self.assertEqual(build_data.profile_data(record), record)

    def test_real_payload_has_no_synthetic_credentials_or_status_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data.js"
            with patch.object(build_data, "OUT", output), \
                    patch.object(build_data.sys, "argv", ["build_data.py", "--as-of", "2026-10-04"]):
                build_data.main()
            payload = json.loads(output.read_text(encoding="utf-8").split("const PS_DATA = ")[1].strip().removesuffix(";"))
        synthetic = [row for row in payload["employees"] if row["dataSource"] == "SYNTHETIC"]
        for row in synthetic:
            for key in ("credentials", "validThru", "ceStart", "ceEnd", "cqr", "city", "state", "zip", "country"):
                self.assertEqual(row[key], "")
            self.assertEqual(row["status"], "NEVER_VERIFIED")
            self.assertIsNone(row["days"])
        emily = next(row for row in payload["employees"] if row["id"] == "E064")
        self.assertEqual(emily["status"], "NEVER_VERIFIED")
        counts = payload["counts"]
        self.assertEqual(counts["total"], counts["current"] + counts["due"] + counts["lapsed"] + counts["never"])
        self.assertEqual((counts["total"], counts["current"], counts["due"], counts["lapsed"], counts["never"]),
                         (103, 3, 1, 0, 99))
        jimmy = next(row for row in payload["employees"] if row["id"] == "DEMO-JIMMY")
        wendy = next(row for row in payload["employees"] if row["id"] == "DEMO-WENDY")
        self.assertEqual((jimmy["days"], jimmy["status"]), (25, "DUE"))
        self.assertEqual((wendy["days"], wendy["status"]), (60, "CURRENT"))
        lucas = next(row for row in payload["managers"] if row["key"] == "Carpenter, Lucas")
        self.assertEqual((lucas["total"], lucas["email"]), (2, "Lucasecarpenter@gmail.com"))

    def test_human_verification_supplies_credentials_without_synthetic_fields(self):
        entry = {
            "employee_id": "E064", "outcome": "verified", "credentials": "R.T.(R)(ARRT)",
            "valid_thru": "10/2027", "verified_on": "2026-10-04",
            "verified_by": "Human verifier", "source": "ARRT directory (human lookup)",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data.js"
            with patch.object(build_data, "OUT", output), \
                    patch.object(build_data.sys, "argv", ["build_data.py", "--as-of", "2026-10-04"]), \
                    patch.object(build_data, "load_verifications", return_value=(
                        {"E064": entry}, {"E064": entry})):
                build_data.main()
            payload = json.loads(output.read_text(encoding="utf-8").split("const PS_DATA = ")[1].strip().removesuffix(";"))
        employee = next(row for row in payload["employees"] if row["id"] == "E064")
        self.assertEqual(employee["credentials"], "R.T.(R)(ARRT)")
        self.assertEqual(employee["validThru"], "10/2027")
        self.assertEqual(employee["status"], "CURRENT")
        self.assertEqual(employee["city"], "")
        self.assertEqual(employee["ceStart"], "")
        self.assertIn("Human", employee["lastVerifiedBy"])
        self.assertEqual(payload["counts"]["verified"], 1)


if __name__ == "__main__":
    unittest.main()
