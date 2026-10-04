"""Loopback-only prod v2 console with an authorized ARRT sanctions updater."""

import argparse
import csv
import json
import logging
import os
import smtplib
import ssl
import subprocess
import sys
import threading
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import parseaddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SUMMARY = ROOT / "v_10" / "output" / "FINDINGS_SUMMARY.txt"
SYNC = ROOT / "v_10" / "output" / "web_sync.json"
DATA = HERE / "assets" / "data.js"
LEDGER = ROOT / "v_5" / "verification_log.csv"
MAIL_LOG = HERE / "notification_log.jsonl"
LEDGER_FIELDS = [
    "logged_at", "employee_id", "last_name", "first_name", "outcome", "credentials",
    "valid_thru", "verified_on", "verified_by", "source", "notes",
]
UPDATE_LOCK = threading.Lock()
STATIC_FILES = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/assets/app.js": ("assets/app.js", "text/javascript"),
    "/assets/data.js": ("assets/data.js", "text/javascript"),
    "/assets/fluid.css": ("assets/fluid.css", "text/css"),
    "/assets/classic.css": ("assets/classic.css", "text/css"),
}


def dashboard() -> dict:
    text = DATA.read_text(encoding="utf-8")
    return json.loads(text.split("const PS_DATA = ", 1)[1].rstrip().removesuffix(";"))


def rebuild_dashboard() -> dict:
    subprocess.run(
        [sys.executable, str(HERE / "build_data.py")], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"), check=True, timeout=60,
    )
    return dashboard()


def record_verification(payload: dict) -> dict:
    employee = next((row for row in dashboard()["employees"]
                     if row["id"] == payload.get("employee_id")), None)
    if employee is None or employee.get("isDemo"):
        raise ValueError("Choose an actual roster employee. Demo records cannot be verified as ARRT evidence.")
    required = ("outcome", "verified_by", "verified_on", "source")
    for key in required:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError("{} is required.".format(key))
    if payload["outcome"] not in ("verified", "discrepancy", "not-found"):
        raise ValueError("Invalid verification outcome.")
    verified_on = date.fromisoformat(payload["verified_on"])
    if verified_on > date.today():
        raise ValueError("Date verified cannot be in the future.")
    valid_thru = payload.get("valid_thru", "").strip()
    if payload["outcome"] == "verified":
        if not payload.get("credentials", "").strip():
            raise ValueError("Record the credentials exactly as shown by ARRT.")
        expiry = datetime.strptime(valid_thru, "%m/%Y")
        if valid_thru != expiry.strftime("%m/%Y") or not 2000 <= expiry.year <= 2100:
            raise ValueError("Valid Through must be MM/YYYY, with year 2000-2100.")
    elif valid_thru:
        raise ValueError("Valid Through only applies to a verified outcome.")
    row = {
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "employee_id": employee["id"], "last_name": employee["last"],
        "first_name": employee["first"],
        **{key: payload.get(key, "").strip() for key in LEDGER_FIELDS
           if key not in ("logged_at", "employee_id", "last_name", "first_name")},
    }
    new_file = not LEDGER.exists() or LEDGER.stat().st_size == 0
    with LEDGER.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    try:
        data = rebuild_dashboard()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            "The verification was saved, but the dashboard refresh failed. "
            "Do not submit again; rebuild the dashboard and check Verification History."
        ) from error
    return {"data": data, "message": "Manual verification saved to the append-only ledger."}


def notification_groups(data: dict) -> tuple[list, list]:
    allowed = {address.strip().lower() for address in os.environ.get(
        "BEACON_SMTP_ALLOWED_RECIPIENTS", "Lucasecarpenter@gmail.com"
    ).split(",") if address.strip()}
    groups, skipped = [], []
    for manager in data["managers"]:
        employees = []
        for employee in data["employees"]:
            if employee["manager"] != manager["key"] or not employee["validThru"]:
                continue
            raw = employee["validThru"]
            if "-" in raw:
                expiry = date.fromisoformat(raw)
            else:
                from calendar import monthrange
                stamp = datetime.strptime(raw, "%m/%Y")
                expiry = date(stamp.year, stamp.month, monthrange(stamp.year, stamp.month)[1])
            days = (expiry - date.today()).days
            if days <= data["windowDays"]:
                employees.append(dict(employee, days=days))
        if not employees:
            continue
        address = manager["email"]
        if not address or address.lower() not in allowed:
            skipped.append({"manager": manager["name"], "reason": "No email or recipient not authorized."})
        else:
            groups.append((manager, employees))
    return groups, skipped


def send_notifications() -> dict:
    host = os.environ.get("BEACON_SMTP_HOST", "")
    sender = os.environ.get("BEACON_SMTP_FROM", "")
    if not host or not sender:
        raise ValueError("Email not sent. Configure BEACON_SMTP_HOST and BEACON_SMTP_FROM "
                         "on the local server, plus SMTP credentials if required.")
    if parseaddr(sender)[1] != sender or "\n" in sender or "\r" in sender:
        raise ValueError("BEACON_SMTP_FROM must be a valid single email address.")
    mode = os.environ.get("BEACON_SMTP_SECURITY", "starttls")
    if mode not in ("starttls", "ssl"):
        raise ValueError("BEACON_SMTP_SECURITY must be starttls or ssl.")
    port = int(os.environ.get("BEACON_SMTP_PORT", "465" if mode == "ssl" else "587"))
    data = rebuild_dashboard()
    groups, skipped = notification_groups(data)
    reports = []
    if not groups:
        return {"reports": reports, "skipped": skipped, "message": "No eligible authorized recipients."}
    client_type = smtplib.SMTP_SSL if mode == "ssl" else smtplib.SMTP
    kwargs = {"context": ssl.create_default_context()} if mode == "ssl" else {}
    with client_type(host, port, timeout=30, **kwargs) as client:
        if mode == "starttls":
            client.starttls(context=ssl.create_default_context())
        user = os.environ.get("BEACON_SMTP_USER", "")
        password = os.environ.get("BEACON_SMTP_PASSWORD", "")
        if user:
            if not password:
                raise ValueError("BEACON_SMTP_PASSWORD is required for the configured SMTP user.")
            client.login(user, password)
        for manager, employees in groups:
            message = EmailMessage()
            message["From"] = sender
            message["To"] = manager["email"]
            demo = all(employee.get("isDemo") for employee in employees)
            message["Subject"] = ("[DEMO] " if demo else "") + "Credential compliance expiration warning"
            lines = [
                "Hello {},".format(manager["name"]),
                "", "These records are lapsed or within the {}-day warning window.".format(data["windowDays"]),
                "Demo records are fictional scenarios, not ARRT verification evidence.", "",
            ]
            for employee in employees:
                lines.extend([
                    "{} ({}){}".format(employee["name"], employee["id"],
                                       " [DEMO]" if employee.get("isDemo") else ""),
                    "Manager: {}".format(manager["name"]),
                    "Expires: {} | Days remaining: {}".format(employee["validThru"], employee["days"]),
                    "Source: {}".format(employee["dataSource"]),
                    "Warning: confirm status and arrange renewal before lapse.", "",
                ])
            message.set_content("\n".join(lines))
            try:
                refused = client.send_message(message)
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
                report = {"manager": manager["name"], "recipient": manager["email"],
                          "status": "Accepted by SMTP server", "employees": len(employees)}
            except smtplib.SMTPException:
                logging.exception("Notification delivery failed for a manager")
                report = {"manager": manager["name"], "status": "Not sent; SMTP delivery failed."}
            reports.append(report)
            with MAIL_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(dict(report, loggedAt=datetime.now().isoformat())) + "\n")
    return {"reports": reports, "skipped": skipped,
            "message": "SMTP results below. Server acceptance does not guarantee inbox delivery."}


def update_sanctions() -> dict:
    """Rebuild the local summary and UI; restore prior files on any failed step."""
    snapshots = {path: path.read_bytes() if path.exists() else None
                 for path in (SUMMARY, SYNC, DATA)}
    try:
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        subprocess.run(
            [sys.executable, str(ROOT / "v_10" / "screen_arrt_sanctions.py"), "--fetch"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            env=environment, check=True, timeout=60,
        )
        subprocess.run(
            [sys.executable, str(HERE / "build_data.py")],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            env=environment, check=True, timeout=60,
        )
        sync = json.loads(SYNC.read_text(encoding="utf-8"))
        text = DATA.read_text(encoding="utf-8")
        payload = json.loads(text.split("const PS_DATA = ", 1)[1].rstrip().removesuffix(";"))
        return {"sync": sync, "data": payload}
    except (OSError, ValueError, subprocess.SubprocessError):
        for path, snapshot in snapshots.items():
            if snapshot is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(snapshot)
        raise


class Handler(BaseHTTPRequestHandler):
    def send_body(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: dict) -> None:
        self.send_body(status, json.dumps(payload).encode("utf-8"), "application/json")

    def valid_host(self) -> bool:
        return self.headers.get("Host") == "127.0.0.1:{}".format(self.server.server_port)

    def do_GET(self) -> None:
        if not self.valid_host():
            self.send_json(403, {"error": "Only the loopback console host is permitted."})
            return
        target = STATIC_FILES.get(urlsplit(self.path).path)
        if target is None:
            self.send_json(404, {"error": "Not found."})
            return
        relative, content_type = target
        try:
            body = (HERE / relative).read_bytes()
        except OSError:
            logging.exception("Unable to read console file")
            self.send_json(500, {"error": "Unable to load this console file."})
            return
        self.send_body(200, body, content_type)

    def do_POST(self) -> None:
        expected_origin = "http://127.0.0.1:{}".format(self.server.server_port)
        endpoints = {
            "/api/arrt-sanctions/update": "arrt-sanctions",
            "/api/verification": "verification",
            "/api/notify-all": "notifications",
        }
        operation = endpoints.get(self.path)
        length = self.headers.get("Content-Length", "0")
        if (not self.valid_host()
                or self.headers.get("Origin") != expected_origin
                or self.headers.get("X-Beacon-Update") != operation
                or not length.isdigit() or int(length) > 16000
                or (operation != "verification" and length != "0")
                or self.headers.get("Transfer-Encoding")):
            self.send_json(403, {"error": "Updates require a same-origin console request."})
            return
        if operation is None:
            self.send_json(404, {"error": "Not found."})
            return
        if not UPDATE_LOCK.acquire(blocking=False):
            self.send_json(409, {"error": "Another update, verification, or notification is already running."})
            return
        try:
            if operation == "verification":
                payload = json.loads(self.rfile.read(int(length)))
                if not isinstance(payload, dict) or any(not isinstance(v, str) for v in payload.values()):
                    raise ValueError("Verification must contain text fields.")
                result = record_verification(payload)
            elif operation == "notifications":
                result = send_notifications()
            else:
                result = update_sanctions()
            self.send_json(200, result)
        except subprocess.CalledProcessError as error:
            logging.exception("ARRT updater command failed")
            self.send_json(502, {"error": (error.stderr or error.stdout).strip()
                                or "ARRT update failed. Previous data was retained."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except RuntimeError as error:
            logging.exception("Saved verification refresh failed")
            self.send_json(500, {"error": str(error)})
        except (OSError, smtplib.SMTPException, subprocess.SubprocessError):
            logging.exception("ARRT updater failed")
            self.send_json(502, {"error": "Operation failed. Check the local server log. "
                                "Do not assume an email was sent or a verification saved."})
        finally:
            UPDATE_LOCK.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Prod v2 updater: http://127.0.0.1:{}".format(server.server_port), flush=True)
    print("Web updates require ARRT permission. No employee data is sent to ARRT.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
