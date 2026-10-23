from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "synthetic"
sys.path.insert(0, str(ROOT))

from analyze import main
from batch_processor import batch_process
from filename_parser import list_data_files, scan_directory
from profile_loader import ExperimentProfile


class InputValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clean-number-input-")
        self.root = Path(self.temporary.name)
        self.data = self.root / "compression"
        self.data.mkdir()
        self.output = self.root / "output"
        self.profile = ExperimentProfile.from_yaml(str(EXAMPLES / "experiment.yaml"))

    def tearDown(self):
        self.temporary.cleanup()

    def arguments(self):
        return ["--dir", str(self.data), "--output", str(self.output),
                "--config", str(EXAMPLES / "experiment.yaml"),
                "--kind", "compression", "--no-plot", "--phase2-only"]

    def fixture(self):
        source = self.data / "d28control1-1.xls"
        shutil.copyfile(EXAMPLES / "input" / "compression" / source.name, source)
        return source

    def test_file_discovery_accepts_case_variants_and_excludes_directories(self):
        for name in ("a.XLS", "b.XlSx", "notes.csv"):
            (self.data / name).write_text("discovery only", encoding="utf-8")
        (self.data / "folder.xls").mkdir()
        (self.data / "folder.xlsx").mkdir()
        self.assertEqual(["a.XLS", "b.XlSx"],
                         [Path(path).name for path in list_data_files(str(self.data))])

    def test_group_discovery_does_not_create_specimens_for_directories(self):
        self.fixture()
        (self.data / "d28treated1-1.xlsx").mkdir()
        groups = scan_directory(str(self.data), profile=self.profile)
        self.assertEqual({"d28_control"}, set(groups))
        self.assertEqual(["d28control1-1.xls"],
                         [info.filename for info in groups["d28_control"]])

    def test_empty_batch_rejects_input_before_creating_output(self):
        (self.data / "notes.txt").write_text("not a data file", encoding="utf-8")
        (self.data / "folder.xls").mkdir()
        with self.assertRaisesRegex(ValueError, "No .xls/.xlsx data files found"):
            batch_process(str(self.data), str(self.output), plot=False,
                          exp_type="compression", profile=self.profile)
        self.assertFalse(self.output.exists())

    def test_empty_batch_preserves_existing_summary(self):
        self.output.mkdir()
        summary = self.output / "summary.csv"
        before = b"filename,status\nprevious.xls,ok\n"
        summary.write_bytes(before)
        with self.assertRaisesRegex(ValueError, "No .xls/.xlsx data files found"):
            batch_process(str(self.data), str(self.output), plot=False,
                          exp_type="compression", profile=self.profile)
        self.assertEqual(before, summary.read_bytes())

    def test_batch_processes_real_file_alongside_suffix_matching_directory(self):
        source = self.fixture()
        before = source.read_bytes()
        (self.data / "d28treated1-1.xlsx").mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            summary = batch_process(str(self.data), str(self.output), plot=False,
                                    exp_type="compression", profile=self.profile)
        self.assertEqual([source.name], summary["filename"].tolist())
        self.assertEqual(["ok"], summary["status"].tolist())
        self.assertAlmostEqual(summary.iloc[0]["strength_MPa"], 60.0, places=6)
        self.assertEqual(before, source.read_bytes())

    def test_empty_cli_has_clear_error_and_creates_no_output(self):
        run = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "analyze.py"),
                              *self.arguments()], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(0, run.returncode)
        self.assertIn("No .xls/.xlsx data files found", run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertFalse(self.output.exists())

    def test_empty_cli_with_overwrite_preserves_previous_output(self):
        self.output.mkdir()
        previous = {"summary.csv": b"previous summary", "experiment_manifest.yaml": b"previous config"}
        for name, content in previous.items():
            (self.output / name).write_bytes(content)
        with self.assertRaisesRegex(SystemExit, "No .xls/.xlsx data files found"):
            main([*self.arguments(), "--overwrite"])
        self.assertEqual(previous, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_cli_ignores_suffix_matching_directory_in_processing_manifest(self):
        source = self.fixture()
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        (self.data / "d28treated1-1.xls").mkdir()
        run = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "analyze.py"),
                              *self.arguments()], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)
        summary = pd.read_csv(self.output / "summary.csv")
        manifest = json.loads((self.output / "processing_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([source.name], summary["filename"].tolist())
        self.assertEqual("success", manifest["status"])
        self.assertEqual([source.name], [record["path"] for record in manifest["input"]["files"]])
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
