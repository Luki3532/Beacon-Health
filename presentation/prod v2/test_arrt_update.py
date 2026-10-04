import importlib.util
import http.client
import io
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import server


spec = importlib.util.spec_from_file_location(
    "sanctions", server.ROOT / "v_10" / "screen_arrt_sanctions.py"
)
sanctions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sanctions)

TABLE = (
    "<table><tr><th>Name</th><th>ARRT ID</th><th>Sanction</th></tr>"
    "<tr><td>Example, Alex</td><td>1234</td><td>Revoke</td></tr></table>"
)


def response(body: str, content_type: str = "text/html") -> io.BytesIO:
    result = io.BytesIO(body.encode("utf-8"))
    result.headers = {"Content-Type": content_type}
    return result


class RetrievalTests(unittest.TestCase):
    def test_complete_table(self):
        with patch.object(sanctions.urllib.request, "urlopen", return_value=response(TABLE)):
            rows, total = sanctions.fetch_rows(sanctions.LIST_URL)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ARRT ID"], "1234")
        self.assertIsNone(total)

    def test_truncated_table_rejected(self):
        with patch.object(sanctions.urllib.request, "urlopen",
                          return_value=response(TABLE.removesuffix("</table>"))):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                sanctions.fetch_rows(sanctions.LIST_URL)

    def test_bad_row_rejected(self):
        body = TABLE.replace("<td>1234</td>", "")
        with patch.object(sanctions.urllib.request, "urlopen", return_value=response(body)):
            with self.assertRaisesRegex(ValueError, "columns"):
                sanctions.fetch_rows(sanctions.LIST_URL)

    def test_partial_fetch_does_not_overwrite_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.txt"
            summary.write_text("previous evidence", encoding="utf-8")
            with patch.object(sanctions, "SUMMARY_FILE", summary), \
                    patch.object(sanctions, "fetch_rows", return_value=([{"Name": "Example"}], 2)):
                with self.assertRaisesRegex(SystemExit, "partial list"):
                    sanctions.screen(fetch=True)
            self.assertEqual(summary.read_text(encoding="utf-8"), "previous evidence")

    def test_json_total_is_preserved(self):
        body = json.dumps({"data": [{"Name": "Example"}], "recordsTotal": 20})
        with patch.object(sanctions.urllib.request, "urlopen",
                          return_value=response(body, "application/json")):
            rows, total = sanctions.fetch_rows(sanctions.LIST_URL)
        self.assertEqual(len(rows), 1)
        self.assertEqual(total, 20)

    def test_success_stores_metadata_and_matching_evidence_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(sanctions, "OUTPUT", root), \
                    patch.object(sanctions, "SUMMARY_FILE", root / "summary.txt"), \
                    patch.object(sanctions, "WEB_SYNC_FILE", root / "sync.json"), \
                    patch.object(sanctions, "fetch_rows", return_value=(
                        [{"Name": "Example, Alex", "ARRT ID": "1234"},
                         {"Name": "Unmatched, Pat", "ARRT ID": "5678"}], 2)), \
                    patch.object(sanctions, "read_csv", return_value=[
                        {"employee_id": "E001", "first_name": "Alex", "last_name": "Example"}
                    ]):
                sanctions.screen(fetch=True)
            sync = json.loads((root / "sync.json").read_text())
            self.assertEqual((sync["records"], sync["people"], sync["flagged"]), (2, 1, 1))
            summary = (root / "summary.txt").read_text()
            self.assertIn("E001", summary)
            self.assertNotIn("Unmatched", summary)


class UpdateTests(unittest.TestCase):
    def test_rebuild_failure_restores_all_prior_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary, sync, data = (root / name for name in ("summary", "sync", "data"))
            summary.write_bytes(b"previous summary")
            data.write_bytes(b"previous dashboard")

            def run(*_args, **_kwargs):
                summary.write_bytes(b"new summary")
                sync.write_bytes(b"new metadata")
                data.write_bytes(b"broken dashboard")
                raise subprocess.CalledProcessError(1, "update", stderr="test failure")

            with patch.multiple(server, SUMMARY=summary, SYNC=sync, DATA=data), \
                    patch.object(server.subprocess, "run", side_effect=run):
                with self.assertRaises(subprocess.CalledProcessError):
                    server.update_sanctions()
            self.assertEqual(summary.read_bytes(), b"previous summary")
            self.assertEqual(data.read_bytes(), b"previous dashboard")
            self.assertFalse(sync.exists())

    def test_success_returns_saved_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary, sync, data = (root / name for name in ("summary", "sync", "data"))

            def run(*_args, **_kwargs):
                summary.write_text("screened")
                sync.write_text('{"records": 2}')
                data.write_text('const PS_DATA = {"employees": []};')

            with patch.multiple(server, SUMMARY=summary, SYNC=sync, DATA=data), \
                    patch.object(server.subprocess, "run", side_effect=run):
                result = server.update_sanctions()
            self.assertEqual(result["sync"]["records"], 2)
            self.assertEqual(result["data"]["employees"], [])


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.server = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        self.origin = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_cross_origin_update_rejected(self):
        with patch.object(server, "update_sanctions") as update:
            self.connection.request("POST", "/api/arrt-sanctions/update", headers={
                "Origin": "https://example.com", "X-Beacon-Update": "arrt-sanctions"
            })
            result = self.connection.getresponse()
            self.assertEqual(result.status, 403)
            result.read()
            update.assert_not_called()

    def test_same_origin_update_returns_saved_data(self):
        with patch.object(server, "update_sanctions",
                          return_value={"sync": {"records": 2}, "data": {"employees": []}}):
            self.connection.request("POST", "/api/arrt-sanctions/update", headers={
                "Origin": self.origin, "X-Beacon-Update": "arrt-sanctions"
            })
            result = self.connection.getresponse()
            self.assertEqual(result.status, 200)
            self.assertEqual(json.loads(result.read())["sync"]["records"], 2)

    def test_concurrent_update_rejected(self):
        server.UPDATE_LOCK.acquire()
        try:
            self.connection.request("POST", "/api/arrt-sanctions/update", headers={
                "Origin": self.origin, "X-Beacon-Update": "arrt-sanctions"
            })
            result = self.connection.getresponse()
            self.assertEqual(result.status, 409)
            result.read()
        finally:
            server.UPDATE_LOCK.release()

    def test_repository_files_are_not_served(self):
        self.connection.request("GET", "/v_1/employee_data.csv")
        result = self.connection.getresponse()
        self.assertEqual(result.status, 404)
        result.read()


if __name__ == "__main__":
    unittest.main()
