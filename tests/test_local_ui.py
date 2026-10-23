from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from local_ui import LocalApp, LocalServer, UIError


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clean-number-ui-")
        self.folder = Path(self.temporary.name)
        self.app = LocalApp(self.folder / "state")
        self.config = self.app.template()

    def tearDown(self):
        self.app.close()
        self.temporary.cleanup()

    def payload(self, kind="compression"):
        return {"input_dir": str(ROOT / "examples/synthetic/input" / kind),
                "output_base": str(self.folder / "results"), "kind": kind,
                "threshold": 0.25, "config": copy.deepcopy(self.config)}

    def finish(self, record):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            record = self.app.run(record["id"])
            if record["status"] not in {"queued", "running"}:
                return record
            time.sleep(0.1)
        self.fail("Synthetic analysis did not finish within 90 seconds")

    def test_inspection_does_not_modify_inputs_and_loads_project_config(self):
        source = ROOT / "examples/synthetic/input/compression"
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
        data = self.app.inspect({"input_dir": str(source)})
        self.assertEqual(data["counts"], {"total": 4, "valid": 4, "invalid": 0})
        self.assertEqual(data["conditions"], ["control", "treated"])
        self.assertEqual(data["config"]["condition_mapping"], self.config["condition_mapping"])
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})

    def test_new_folder_creates_explicit_neutral_mapping(self):
        source = self.folder / "new-experiment"
        source.mkdir()
        (source / "d28自定义1-1.xls").write_text("not processed during inspection", encoding="utf-8")
        result = self.app.inspect({"input_dir": str(source)})
        self.assertEqual(set(result["config"]["condition_mapping"]), {"自定义"})
        self.assertNotIn("control", result["config"]["condition_mapping"])
        self.assertEqual(result["config"]["project"]["name"], "new-experiment")

    def test_saved_preset_keeps_unknown_fields_factors_and_units(self):
        self.config["custom_notes"] = {"nested": ["keep", 0, False]}
        self.config["methods"]["flexural"]["geometry"]["span_mm"] = 120
        payload = self.payload("flexural")
        payload.update(name="弯曲 120 mm", config=self.config)
        saved = self.app.save_preset(payload)
        loaded = self.app.preset(saved["id"])
        self.assertEqual(loaded["config"]["custom_notes"], self.config["custom_notes"])
        self.assertEqual(loaded["config"]["condition_mapping"], self.config["condition_mapping"])
        self.assertEqual(loaded["config"]["methods"]["flexural"]["geometry"]["span_mm"], 120)
        self.assertEqual(loaded["threshold"], 0.25)
        with self.assertRaises(UIError):
            self.app.preset("../../outside")

    def test_invalid_numbers_and_geometry_are_rejected_before_running(self):
        for value in ("nan", "inf", -1, None):
            payload = self.payload()
            payload["threshold"] = value
            with self.subTest(threshold=value), self.assertRaises(UIError):
                self.app.start_run(payload)
        payload = self.payload("flexural")
        payload["config"]["methods"]["flexural"]["geometry"]["depth_mm"] = 0
        with self.assertRaises(UIError):
            self.app.start_run(payload)
        self.assertEqual(self.app.runs, {})

    def test_run_rejects_writing_into_input_or_source(self):
        for output in (ROOT / "examples/synthetic/input/compression", ROOT / "ui"):
            payload = self.payload()
            payload["output_base"] = str(output)
            with self.subTest(output=str(output)), self.assertRaises(UIError):
                self.app.start_run(payload)

    def test_compression_end_to_end_matches_independent_fixture_expectation(self):
        payload = self.payload()
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(payload["input_dir"]).glob("*.xls")}
        payload["config"]["custom_notes"] = {"unchanged": True}
        record = self.finish(self.app.start_run(payload))
        self.assertEqual(record["status"], "succeeded", "\n".join(record["logs"][-15:]))
        results = self.app.results(record["id"])
        self.assertEqual(results["stats"]["succeeded"], 4)
        self.assertEqual(results["stats"]["specimens"], 2)
        control = next(row for row in results["rows"] if row["filename"] == "d28control1-1.xls")
        self.assertAlmostEqual(float(control["strength_MPa"]), 60, places=6)
        self.assertAlmostEqual(float(control["modulus_GPa"]), 10, places=6)
        self.assertTrue(results["figures"])
        snapshot = yaml.safe_load((Path(record["output_dir"]) / "experiment_manifest.yaml").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["custom_notes"], {"unchanged": True})
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})
        with self.assertRaises(UIError):
            self.app.result_file(record["id"], "../not-a-result.csv")
        saved = LocalApp(self.app.state_dir)
        self.assertEqual(saved.run(record["id"])["status"], "succeeded")

    def test_flexural_geometry_is_applied_by_existing_cli(self):
        payload = self.payload("flexural")
        payload["config"]["methods"]["flexural"]["geometry"]["span_mm"] = 120
        record = self.finish(self.app.start_run(payload))
        self.assertEqual(record["status"], "succeeded", "\n".join(record["logs"][-15:]))
        treated = next(row for row in self.app.results(record["id"])["rows"] if row["filename"] == "d28treated1.xls")
        # Rectangular three-point bending stress is proportional to span;
        # diagnostic modulus is proportional to its cube.
        self.assertAlmostEqual(float(treated["strength_MPa"]), 168.75 * 1.2, places=5)
        self.assertAlmostEqual(float(treated["modulus_GPa"]), 11.71875 * 1.2 ** 3, places=5)

    def test_failed_input_remains_failed_in_results(self):
        source = self.folder / "bad-input"
        source.mkdir()
        shutil.copyfile(ROOT / "examples/synthetic/input/compression/d28control1-1.xls", source / "d28control1-1.xls")
        (source / "d28treated1-1.xls").write_text("synthetic\n时间 (s)\t应力 (MPa)\n0\t0\n1\t5\n", encoding="gbk")
        payload = self.payload()
        payload["input_dir"] = str(source)
        record = self.finish(self.app.start_run(payload))
        self.assertEqual(record["status"], "failed")
        results = self.app.results(record["id"])
        self.assertEqual(results["stats"]["files"], 2)
        self.assertEqual(results["stats"]["failed"], 1)
        self.assertEqual(results["stats"]["succeeded"], 1)
        self.assertTrue(any(row["status"] != "ok" for row in results["rows"]))
        failed_row = next(row for row in results["rows"] if row["status"] != "ok")
        self.assertTrue(failed_row["error_msg"])

    def test_cancel_does_not_claim_success_and_output_is_preserved(self):
        record = self.app.start_run(self.payload())
        cancelled = self.app.cancel(record["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.app.close()
        self.assertEqual(self.app.run(record["id"])["status"], "cancelled")
        self.assertTrue((self.app.state_dir / "runs.json").is_file())

    def test_http_session_origin_and_static_contract(self):
        server = LocalServer(("127.0.0.1", 0), self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/") as response:
                html = response.read().decode("utf-8")
                self.assertIn(self.app.token, html)
                self.assertNotIn("__API_TOKEN__", html)
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/api/bootstrap")
            self.assertEqual(error.exception.code, 403)
            headers = {"X-Clean-Number-Token": self.app.token}
            with urlopen(Request(base + "/api/bootstrap", headers=headers)) as response:
                self.assertIn("examples", json.load(response))
            headers.update(Origin="https://example.invalid", **{"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/runs", data=b"{}", headers=headers))
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(self.app.runs, {})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
