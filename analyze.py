#!/usr/bin/env python3
"""Run one explicitly bounded clean_number analysis.

The command only reads ``data_dir`` and writes below the required
``output_dir``. It never discovers sibling projects or creates a project-wide
summary implicitly.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("analyze")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load_profile(data_dir: str, config_path: str | None):
    from profile_loader import ExperimentProfile, try_load

    if config_path:
        profile = ExperimentProfile.from_yaml(config_path)
        if profile is None:
            raise ValueError(f"Configuration file is empty or unreadable: {config_path}")
        return profile
    return try_load(data_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process one bounded directory of instrument data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python analyze.py -d examples/synthetic/input/compression "
            "-c examples/synthetic/experiment.yaml -k compression -o run-output"
        ),
    )
    parser.add_argument("-d", "--dir", required=True, help="Input data directory.")
    parser.add_argument("-c", "--config", default=None, help="Explicit experiment.yaml path.")
    parser.add_argument(
        "-k", "--kind", choices=("compression", "flexural"), default=None,
        help="Test method. Required unless it is unambiguously detected from the path, RTF, or config.",
    )
    parser.add_argument("-o", "--output", required=True, help="Output directory for this run.")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Allow writing into a non-empty output directory explicitly.",
    )
    parser.add_argument("-t", "--threshold", type=float, default=0.25, help="Force threshold in kN.")
    parser.add_argument("--no-plot", action="store_true", help="Skip plot generation.")
    parser.add_argument("--phase2-only", action="store_true", help="Skip report generation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.dir):
        raise SystemExit(f"Input directory does not exist: {args.dir}")
    output_path = os.path.abspath(args.output)
    if os.path.isdir(output_path) and any(os.scandir(output_path)) and not args.overwrite:
        raise SystemExit(
            f"Output directory is not empty: {args.output}. Choose a new directory or pass --overwrite."
        )

    from context import AnalysisContext
    from experiment_type import ExperimentKind

    profile = _load_profile(args.dir, args.config)
    config_kind = profile.info.get("kind") if profile else None
    kind = args.kind or config_kind
    ctx = AnalysisContext.create(args.dir, output_override=output_path, explicit_kind=kind)
    if ctx.experiment_type.kind is ExperimentKind.UNKNOWN:
        raise SystemExit(
            "Test type is unknown; pass --kind compression|flexural or set project.kind in the config."
        )

    paths = ctx.paths
    paths.ensure_dirs()
    log.info("Input directory: %s", ctx.data_dir)
    log.info("Test type: %s", ctx.experiment_type.kind.value)
    log.info("Output directory: %s", paths.output_dir)

    from profile_loader import write_manifest_snapshot
    write_manifest_snapshot(profile, str(paths.output_dir))

    from batch_processor import batch_process
    summary = batch_process(
        data_dir=str(ctx.data_dir), output_dir=str(paths.output_dir),
        figures_dir=str(paths.figures), force_threshold=args.threshold,
        plot=not args.no_plot, exp_type=ctx.experiment_type, profile=profile,
    )

    from group_processor import process_all_groups
    groups = process_all_groups(
        str(ctx.data_dir), str(paths.output_dir), exp_type=ctx.experiment_type, profile=profile
    )

    from table_generator import generate_table
    generate_table(groups, str(paths.output_dir), tables_dir=str(paths.tables))

    from stats_analyzer import analyze_statistics
    units, _, _ = analyze_statistics(summary, groups, str(paths.tables))
    if not args.no_plot:
        from stats_plotter import generate_statistical_plots
        generate_statistical_plots(units, str(paths.figures))
        from figure_composer import compose_all_figures
        compose_all_figures(
            groups, str(paths.output_dir), figures_dir=str(paths.figures), exp_type=ctx.experiment_type
        )

    if not args.phase2_only:
        from comparison_engine import build_comparison_matrix
        from report_builder import generate_report
        comparison = build_comparison_matrix(groups, metric="strength_mean")
        generate_report(
            data_dir=str(ctx.data_dir), output_dir=str(paths.output_dir),
            reports_dir=str(paths.reports), df_summary=summary,
            groups_results=groups, comparison_matrix=comparison,
            exp_type=ctx.experiment_type, profile=profile,
        )

    log.info("Completed: %d input records; output=%s", len(summary), paths.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
