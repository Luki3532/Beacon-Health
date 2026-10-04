import csv
import os
import smtplib
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import server


def email_payload():
    manager = {"key": "Carpenter, Lucas", "name": "Lucas Carpenter",
               "email": "Lucasecarpenter@gmail.com"}
    employees = [
        {"id": "DEMO-JIMMY", "name": "Jimmy John", "manager": manager["key"],
         "validThru": (date.today() + timedelta(days=25)).isoformat(),
         "isDemo": True, "dataSource": "DEMO COMPLIANCE SCENARIO"},
        {"id": "DEMO-WENDY", "name": "Wendy King", "manager": manager["key"],
         "validThru": (date.today() + timedelta(days=60)).isoformat(),
         "isDemo": True, "dataSource": "DEMO COMPLIANCE SCENARIO"},
    ]
    return {"managers": [manager], "employees": employees, "windowDays": 30}


class EmailTests(unittest.TestCase):
    def test_jimmy_selected_wendy_excluded(self):
        with patch.dict(os.environ, {}, clear=True):
            groups, skipped = server.notification_groups(email_payload())
        self.assertEqual([row["id"] for row in groups[0][1]], ["DEMO-JIMMY"])
        self.assertEqual(skipped, [])

    def test_unauthorized_recipient_skipped(self):
        data = email_payload()
        data["managers"][0]["email"] = "someone@example.com"
        with patch.dict(os.environ, {}, clear=True):
            groups, skipped = server.notification_groups(data)
        self.assertEqual(groups, [])
        self.assertEqual(len(skipped), 1)

    def test_no_configuration_does_not_send(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(server.smtplib, "SMTP") as smtp:
            with self.assertRaisesRegex(ValueError, "Email not sent"):
                server.send_notifications()
            smtp.assert_not_called()

    def test_smtp_message_contains_jimmy_and_demo_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            client = MagicMock()
            client.send_message.return_value = {}
            with patch.dict(os.environ, {
                "BEACON_SMTP_HOST": "smtp.example.com",
                "BEACON_SMTP_FROM": "sender@example.com",
                "BEACON_SMTP_SECURITY": "starttls", "BEACON_SMTP_USER": "",
                "BEACON_SMTP_ALLOWED_RECIPIENTS": "Lucasecarpenter@gmail.com",
            }), patch.object(server, "rebuild_dashboard", return_value=email_payload()), \
                    patch.object(server, "MAIL_LOG", Path(directory) / "mail.jsonl"), \
                    patch.object(server.smtplib, "SMTP") as smtp:
                smtp.return_value.__enter__.return_value = client
                result = server.send_notifications()
            message = client.send_message.call_args.args[0]
            self.assertEqual(message["To"], "Lucasecarpenter@gmail.com")
            self.assertIn("Jimmy John", message.get_content())
            self.assertIn("Days remaining: 25", message.get_content())
            self.assertNotIn("Wendy King", message.get_content())
            self.assertIn("[DEMO]", message["Subject"])
            self.assertEqual(result["reports"][0]["status"], "Accepted by SMTP server")
            client.starttls.assert_called_once()

    def test_smtp_failure_not_reported_as_sent(self):
        with tempfile.TemporaryDirectory() as directory:
            client = MagicMock()
            client.send_message.side_effect = smtplib.SMTPDataError(550, b"rejected")
            with patch.dict(os.environ, {
                "BEACON_SMTP_HOST": "smtp.example.com",
                "BEACON_SMTP_FROM": "sender@example.com",
                "BEACON_SMTP_SECURITY": "starttls", "BEACON_SMTP_USER": "",
                "BEACON_SMTP_ALLOWED_RECIPIENTS": "Lucasecarpenter@gmail.com",
            }), patch.object(server, "rebuild_dashboard", return_value=email_payload()), \
                    patch.object(server, "MAIL_LOG", Path(directory) / "mail.jsonl"), \
                    patch.object(server.smtplib, "SMTP") as smtp:
                smtp.return_value.__enter__.return_value = client
                result = server.send_notifications()
            self.assertIn("Not sent", result["reports"][0]["status"])


class ManualVerificationTests(unittest.TestCase):
    def test_saved_lookup_is_append_only(self):
        employee = {"id": "E001", "last": "Example", "first": "Alex", "isDemo": False}
        payload = {
            "employee_id": "E001", "outcome": "verified", "credentials": "R.T.(R)(ARRT)",
            "valid_thru": "10/2027", "verified_on": date.today().isoformat(),
            "verified_by": "Human verifier", "source": "ARRT directory (human lookup)",
        }
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.csv"
            with patch.object(server, "LEDGER", ledger), \
                    patch.object(server, "dashboard", return_value={"employees": [employee]}), \
                    patch.object(server, "rebuild_dashboard", return_value={}):
                server.record_verification(payload)
                prior = ledger.read_bytes()
                server.record_verification(dict(payload, outcome="not-found", valid_thru=""))
            self.assertTrue(ledger.read_bytes().startswith(prior))
            with ledger.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["outcome"] for row in rows], ["verified", "not-found"])
            self.assertEqual(rows[0]["verified_by"], "Human verifier")

    def test_demo_is_not_saved_as_arrt_evidence(self):
        with patch.object(server, "dashboard", return_value={
            "employees": [{"id": "DEMO-JIMMY", "isDemo": True}]
        }):
            with self.assertRaisesRegex(ValueError, "Demo records"):
                server.record_verification({"employee_id": "DEMO-JIMMY"})

    def test_unnamed_verifier_rejected(self):
        with patch.object(server, "dashboard", return_value={
            "employees": [{"id": "E001", "isDemo": False}]
        }):
            with self.assertRaisesRegex(ValueError, "verified_by"):
                server.record_verification({"employee_id": "E001", "outcome": "verified"})


if __name__ == "__main__":
    unittest.main()
