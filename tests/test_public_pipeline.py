from __future__ import annotations

import hashlib
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "synthetic"
sys.path.insert(0, str(ROOT))

from batch_processor import batch_process
from experiment_type import ExperimentKind, detect
from filename_parser import scan_directory
from group_processor import process_all_groups
from process_single import process_single_file
from profile_loader import ExperimentProfile
from processing_manifest import build_processing_manifest, read_summary_rows


class PublicPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = ExperimentProfile.from_yaml(str(EXAMPLES / "experiment.yaml"))

    def _write_fixture(self, path: Path, headers: list[str], rows: list[list[float]]) -> None:
        lines = ["synthetic fixture", "\t".join(headers)]
        lines.extend("\t".join(str(value) for value in row) for row in rows)
        path.write_text("\n".join(lines) + "\n", encoding="gbk")

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
        result = process_single_file(
            str(source),
            plot=False,
            flexural_mode=True,
            method_config=self.profile.method_config("flexural"),
        )
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["strength_MPa"], 168.75, places=6)
        # Generated slope is 120 kN/mm; the beam factor is 0.09765625.
        self.assertAlmostEqual(result["modulus_GPa"], 11.71875, places=6)

    def test_unavailable_flexural_modulus_stays_missing_in_result_and_plot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "d28control1.xls"
            # Five points through the peak permit generic chord extraction,
            # but are insufficient for the flexural modulus calculation.
            self._write_fixture(
                source,
                ["时间 (s)", "力 (kN)", "变形 (mm)"],
                [[i * 0.1, force, i * 0.1]
                 for i, force in enumerate([0, 1, 2, 3, 4, 3, 2])],
            )
            with patch("process_single.plot_stress_strain") as plot:
                result = process_single_file(
                    str(source), plot=True, output_dir=temp_dir,
                    flexural_mode=True,
                    method_config=self.profile.method_config("flexural"),
                )
            self.assertEqual(result["status"], "ok")
            self.assertAlmostEqual(result["strength_MPa"], 9.375, places=6)
            self.assertIsNone(result["modulus_GPa"])
            plot.assert_called_once()
            self.assertIsNone(plot.call_args.args[1]["modulus_GPa"])

    def test_manifest_flexural_geometry_changes_calculated_strength(self):
        config = copy.deepcopy(yaml.safe_load((EXAMPLES / "experiment.yaml").read_text(encoding="utf-8")))
        config["methods"]["flexural"]["geometry"]["span_mm"] = 80.0
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "experiment.yaml"
            config_path.write_text(
                yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            profile = ExperimentProfile.from_yaml(str(config_path))
            source = EXAMPLES / "input" / "flexural" / "d28treated1.xls"
            result = process_single_file(
                str(source),
                plot=False,
                flexural_mode=True,
                method_config=profile.method_config("flexural"),
            )
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["strength_MPa"], 135.0, places=6)
        # With an 80 mm span the beam factor is 0.05, giving 6 GPa.
        self.assertAlmostEqual(result["modulus_GPa"], 6.0, places=6)

    def test_missing_required_measurement_column_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "d28control1-1.xls"
            self._write_fixture(
                source,
                ["时间 (s)", "力 (kN)", "应力 (MPa)"],
                [[0.0, 0.0, 0.0], [0.1, 10.0, 10.0], [0.2, 20.0, 20.0]],
            )
            result = process_single_file(
                str(source),
                plot=False,
                flexural_mode=False,
                method_config=self.profile.method_config("compression"),
            )
        self.assertEqual(result["status"], "error")
        self.assertIn("missing required columns", result["error_msg"])

    def test_unknown_units_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "d28control1-1.xls"
            self._write_fixture(
                source,
                ["时间 (s)", "应力", "应变 (%)"],
                [[0.0, 0.0, 0.0], [0.1, 10.0, 0.1], [0.2, 20.0, 0.2]],
            )
            result = process_single_file(str(source), plot=False, flexural_mode=False)
        self.assertEqual(result["status"], "error")
        self.assertIn("unit", result["error_msg"])

    def test_millisecond_time_unit_does_not_match_seconds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "d28control1-1.xls"
            self._write_fixture(
                source,
                ["时间 (ms)", "应力 (MPa)", "应变 (%)"],
                [[0.0, 0.0, 0.0], [0.1, 10.0, 0.1], [0.2, 20.0, 0.2]],
            )
            result = process_single_file(str(source), plot=False, flexural_mode=False)
        self.assertEqual(result["status"], "error")
        self.assertIn("time unit", result["error_msg"])

    def test_duplicate_semantic_columns_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "d28control1.xls"
            self._write_fixture(
                source,
                ["时间 (s)", "力 (kN)", "加载力 (kN)", "变形 (mm)"],
                [[0.0, 0.0, 0.0, 0.0], [0.1, 10.0, 10.0, 0.1], [0.2, 20.0, 20.0, 0.2]],
            )
            result = process_single_file(str(source), plot=False, flexural_mode=True)
        self.assertEqual(result["status"], "error")
        self.assertIn("Multiple columns map to force_kN", result["error_msg"])

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

    def test_processing_manifest_records_hashes_and_partial_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data = root / "input"
            output = root / "output"
            data.mkdir()
            output.mkdir()
            source = data / "sample.xls"
            source.write_bytes(b"synthetic")
            (output / "summary.csv").write_text(
                "filename,raw_sha256,status,method,method_config_hash,is_duplicate_content\n"
                f"{source.name},{hashlib.sha256(source.read_bytes()).hexdigest()},ok,compression,abc,False\n"
                "missing.xls,,error,compression,abc,False\n",
                encoding="utf-8",
            )
            manifest = build_processing_manifest(
                data_dir=data,
                output_dir=output,
                run_id="synthetic-partial",
                force_threshold=0.25,
                summary_rows=read_summary_rows(output / "summary.csv"),
                tool_root=ROOT,
            )
        self.assertEqual(manifest["status"], "partial_failure")
        self.assertEqual(manifest["input"]["successful_files"], 1)
        self.assertEqual(manifest["input"]["failed_files"], 1)
        self.assertEqual(manifest["input"]["files"][0]["status"], "ok")
        self.assertEqual(manifest["input"]["files"][1]["status"], "error")


if __name__ == "__main__":
    unittest.main()
