#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_processor.py — 文件夹遍历批处理（目录名驱动，零正则依赖）

核心策略：
  1. 目录名 = 分组标签（用户自己按分组组织文件夹）
  2. 显式分析上下文/目录名决定试验类型，RTF 仅作回退
  3. 扫描所有 .xls；无需文件名正则，未来实验零代码改动

用法:
  python batch_processor.py -d <data_dir> -o <output_dir>
"""

import os
import hashlib
import logging
import argparse

import pandas as pd

from process_single import process_single_file
from parse_rtf import detect_test_type
from experiment_type import detect as detect_experiment_type
from filename_parser import list_data_files, make_specimen_info
from profile_loader import try_load
from processing_overrides import get_file_override

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("batch")


def _sha256_file(filepath: str) -> str:
    digest = hashlib.sha256()
    with open(filepath, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def detect_duplicate_content(filepaths: list[str]) -> dict[str, dict]:
    """Return content-hash metadata without excluding any file automatically."""
    hashes = {filepath: _sha256_file(filepath) for filepath in filepaths}
    by_hash: dict[str, list[str]] = {}
    for filepath, digest in hashes.items():
        by_hash.setdefault(digest, []).append(filepath)

    metadata = {}
    for digest, members in by_hash.items():
        ordered = sorted(members, key=lambda value: os.path.basename(value).casefold())
        canonical = ordered[0]
        for filepath in ordered:
            metadata[filepath] = {
                "raw_sha256": digest,
                "duplicate_group_id": digest[:12] if len(ordered) > 1 else "",
                "duplicate_set_size": len(ordered),
                "is_duplicate_content": len(ordered) > 1,
                "duplicate_of": "" if filepath == canonical else os.path.basename(canonical),
            }
    return metadata


def _normalise_test_type(exp_type) -> str | None:
    """Return ``compression``/``flexural`` for supported context values."""
    if exp_type is None:
        return None

    value = exp_type
    if hasattr(value, "kind"):
        value = value.kind
    if hasattr(value, "value"):
        value = value.value
    value = str(value).lower()

    if value in {"compression", "compressive"}:
        return "compression"
    if value in {"flexural", "bending"}:
        return "flexural"
    return None


def resolve_batch_test_type(data_dir: str, exp_type=None) -> str | None:
    """Resolve one authoritative test type for a homogeneous data directory.

    Priority: caller-provided analysis context, then directory/path detection.
    Per-file RTF detection is retained only as a fallback in ``batch_process``.
    """
    explicit = _normalise_test_type(exp_type)
    if explicit:
        return explicit

    detected = detect_experiment_type(data_dir)
    if detected.kind.value in {"compression", "flexural"}:
        return detected.kind.value
    return None


def batch_process(
    data_dir: str,
    output_dir: str,
    figures_dir: str = None,
    force_threshold: float = 0.25,
    plot: bool = True,
    exp_type = None,
    profile = None,
) -> pd.DataFrame:
    """
    批量处理目录下所有 .xls 文件。

    Parameters
    ----------
    data_dir : str
        数据目录（目录名 = 分组标签）。
    output_dir : str
        输出目录。
    figures_dir : str or None
        图片输出目录。为 None 则用 output_dir。
    force_threshold : float
        力阈值 (kN)。
    plot : bool
        是否生成曲线图。

    Returns
    -------
    pd.DataFrame
        汇总表。
    """
    all_files = list_data_files(data_dir)
    if not all_files:
        raise ValueError(f"No .xls/.xlsx data files found in input directory: {data_dir}")
    profile = profile or try_load(data_dir)
    duplicate_metadata = detect_duplicate_content(all_files)
    
    log.info("数据目录: %s  |  文件数: %d", os.path.basename(os.path.normpath(data_dir)), len(all_files))

    # 数据目录应只包含一种试验。显式上下文/文件夹名称优先于 RTF，
    # 因为部分试验机导出的抗折 RTF 仍带有抗压模板标记。
    directory_test_type = resolve_batch_test_type(data_dir, exp_type=exp_type)
    if directory_test_type:
        log.info("试验类型(目录级): %s", directory_test_type)

    rows = []

    for idx, filepath in enumerate(all_files, 1):
        fname = os.path.basename(filepath)
        log.info("[%d/%d] %s", idx, len(all_files), fname)

        info = make_specimen_info(data_dir, fname, profile=profile)
        if info is None:
            log.warning("文件名无法解析，按未分组文件处理: %s", fname)

        # RTF 只在目录级类型无法确定时回退使用。
        test_type = directory_test_type
        if test_type is None:
            rtf_path = os.path.splitext(filepath)[0] + ".rtf"
            if os.path.isfile(rtf_path):
                test_type = detect_test_type(rtf_path)
            if test_type not in {"compression", "flexural"}:
                raise ValueError(
                    "Test type is unknown. Pass an explicit kind or provide a supported RTF marker."
                )
        method_config = profile.method_config(test_type) if profile is not None else None

        # 图片输出目录：若指定 figures_dir 则单独存放，否则用 output_dir
        plot_dir = figures_dir or output_dir

        # 处理（透传试验类型）
        file_override = get_file_override(filepath)
        res = process_single_file(
            filepath,
            output_dir=plot_dir,
            force_threshold=force_threshold,
            plot=plot,
            flexural_mode=(test_type == "flexural"),
            processing_override=file_override,
            method_config=method_config,
        )

        duplicate = duplicate_metadata[filepath]
        exclude_from_statistics = bool(
            file_override and file_override.get("exclude_from_statistics", False)
        )
        exclusion_reason = ""
        if exclude_from_statistics:
            exclusion_reason = str(
                file_override.get("exclusion_reason")
                or file_override.get("reason")
                or "项目配置明确排除"
            )
        quality_flags = []
        if duplicate["is_duplicate_content"]:
            quality_flags.append("duplicate_content")
        if res.get("override_applied", False):
            quality_flags.append("processing_override")
        if exclude_from_statistics:
            quality_flags.append("excluded_from_statistics")

        row = {
            "filename": fname,
            "group_key": info.group_key if info else "unparsed",
            "group_label": info.group_label if info else "Unparsed",
            "group_label_cn": info.group_label_cn if info else "未解析",
            "group_label_en": info.group_label_en if info else "Unparsed",
            "group_id": info.group_id if info else "",
            "mix_id": info.mix_id if info else "",
            "age_days": info.age if info else None,
            "condition": info.condition if info else "",
            "specimen_id": info.specimen_id if info else None,
            "end_id": info.end_id if info else None,
            "test_type": test_type,
            "method": res.get("method"),
            "formula": res.get("formula"),
            "method_config_hash": res.get("method_config_hash"),
            "modulus_lower_fraction": res.get("modulus_lower_fraction"),
            "modulus_upper_fraction": res.get("modulus_upper_fraction"),
            "span_mm": res.get("span_mm"),
            "width_mm": res.get("width_mm"),
            "depth_mm": res.get("depth_mm"),
            "strength_MPa": res.get("strength_MPa"),
            "modulus_GPa": res.get("modulus_GPa"),
            "data_points": res.get("data_points", 0),
            "raw_data_points": res.get("raw_data_points", 0),
            "override_applied": res.get("override_applied", False),
            "cutoff_time_s": res.get("cutoff_time_s"),
            "cutoff_row": res.get("cutoff_row"),
            "raw_sha256": duplicate["raw_sha256"],
            "duplicate_group_id": duplicate["duplicate_group_id"],
            "duplicate_set_size": duplicate["duplicate_set_size"],
            "is_duplicate_content": duplicate["is_duplicate_content"],
            "duplicate_of": duplicate["duplicate_of"],
            "exclude_from_statistics": exclude_from_statistics,
            "exclusion_reason": exclusion_reason,
            "quality_flags": "|".join(quality_flags),
            "status": res.get("status", "error"),
            "error_msg": res.get("error_msg", ""),
        }
        if info:
            for factor_name, factor_value in info.factors.items():
                row[f"factor_{factor_name}"] = factor_value
        rows.append(row)

    df = pd.DataFrame(rows)

    # 保存 CSV
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "summary.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log.info("汇总已保存: %s", csv_path)

    # 打印
    print(f"\n{'='*75}")
    print(f"{'文件名':<25s} {'分组':<15s} {'强度':<10s} {'模量':<10s} {'状态':<8s}")
    print(f"{'-'*75}")
    for _, row in df.iterrows():
        s = f"{row['strength_MPa']:.3f}" if pd.notna(row['strength_MPa']) else "N/A"
        m = f"{row['modulus_GPa']:.3f}" if pd.notna(row['modulus_GPa']) else "N/A"
        print(f"{row['filename']:<25s} {row['group_key']:<15s} {s:<10s} {m:<10s} {row['status']:<8s}")
    print(f"{'='*75}")

    return df


def main():
    parser = argparse.ArgumentParser(description="批处理（目录名驱动）")
    parser.add_argument("-d", "--dir", type=str, required=True, help="数据目录")
    parser.add_argument("-o", "--output", type=str, default="output", help="输出目录")
    parser.add_argument("-t", "--threshold", type=float, default=0.25, help="力阈值/kN")
    parser.add_argument("--no-plot", action="store_true", help="不生成图表")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        log.error("目录不存在: %s", args.dir)
        sys.exit(1)

    batch_process(
        data_dir=args.dir,
        output_dir=args.output,
        force_threshold=args.threshold,
        plot=not args.no_plot,
    )


if __name__ == "__main__":
    import sys
    main()
