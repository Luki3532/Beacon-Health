"""Loopback-only prod v2 console with an authorized ARRT sanctions updater."""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SUMMARY = ROOT / "v_10" / "output" / "FINDINGS_SUMMARY.txt"
SYNC = ROOT / "v_10" / "output" / "web_sync.json"
DATA = HERE / "assets" / "data.js"
UPDATE_LOCK = threading.Lock()
STATIC_FILES = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/assets/app.js": ("assets/app.js", "text/javascript"),
    "/assets/data.js": ("assets/data.js", "text/javascript"),
    "/assets/fluid.css": ("assets/fluid.css", "text/css"),
    "/assets/classic.css": ("assets/classic.css", "text/css"),
}


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
        if (not self.valid_host()
                or self.headers.get("Origin") != expected_origin
                or self.headers.get("X-Beacon-Update") != "arrt-sanctions"
                or self.headers.get("Content-Length", "0") != "0"
                or self.headers.get("Transfer-Encoding")):
            self.send_json(403, {"error": "Updates require a same-origin console request."})
            return
        if self.path != "/api/arrt-sanctions/update":
            self.send_json(404, {"error": "Not found."})
            return
        if not UPDATE_LOCK.acquire(blocking=False):
            self.send_json(409, {"error": "An ARRT update is already running."})
            return
        try:
            self.send_json(200, update_sanctions())
        except subprocess.CalledProcessError as error:
            logging.exception("ARRT updater command failed")
            self.send_json(502, {"error": (error.stderr or error.stdout).strip()
                                or "ARRT update failed. Previous data was retained."})
        except (OSError, ValueError, subprocess.SubprocessError):
            logging.exception("ARRT updater failed")
            self.send_json(502, {"error": "ARRT update failed. Previous data was retained; "
                                "see the local server log for details."})
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
