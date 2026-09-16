from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "synthetic"
sys.path.insert(0, str(ROOT))

from batch_processor import batch_process
from experiment_type import ExperimentKind, detect
from filename_parser import scan_directory
from group_processor import process_all_groups
from process_single import process_single_file
from profile_loader import ExperimentProfile


class PublicPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = ExperimentProfile.from_yaml(str(EXAMPLES / "experiment.yaml"))

    def test_manifest_maps_synthetic_conditions(self):
        groups = scan_directory(str(EXAMPLES / "input" / "compression"), profile=self.profile)
        self.assertEqual(set(groups), {"d28_control", "d28_treated"})
        self.assertEqual(groups["d28_control"][0].mix_id, "control")

    def test_unknown_type_is_not_silently_compression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(detect(temp_dir).kind, ExperimentKind.UNKNOWN)

    def test_compression_fixture_has_independent_result_and_preserves_input(self):
        source = EXAMPLES / "input" / "compression" / "d28control1-1.xls"
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        result = process_single_file(str(source), plot=False, flexural_mode=False)
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["strength_MPa"], 60.0, places=6)
        self.assertAlmostEqual(result["modulus_GPa"], 10.0, places=6)
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_flexural_fixture_uses_explicit_flexural_path(self):
        source = EXAMPLES / "input" / "flexural" / "d28treated1.xls"
        result = process_single_file(str(source), plot=False, flexural_mode=True)
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["strength_MPa"], 168.75, places=6)

    def test_bounded_batch_and_group_outputs_use_only_requested_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output"
            summary = batch_process(
                str(EXAMPLES / "input" / "compression"), str(output),
                plot=False, exp_type="compression", profile=self.profile,
            )
            groups = process_all_groups(
                str(EXAMPLES / "input" / "compression"), str(output),
                exp_type="compression", profile=self.profile,
            )
            self.assertEqual(len(summary), 4)
            self.assertTrue((output / "summary.csv").is_file())
            self.assertEqual({item["n"] for item in groups}, {1})
            self.assertEqual(
                {path for path in Path(temp_dir).rglob("*") if path.is_file()},
                {output / "summary.csv"},
            )


if __name__ == "__main__":
    unittest.main()
