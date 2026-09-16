#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
group_processor.py — 分组聚合：平均曲线 + 统计量

从 batch_processor 的结果出发，按组聚合：
  1. 读取每个文件的对齐后曲线
  2. 插值到统一网格（抗压=应变%, 抗折=位移mm）
  3. 计算组均值 ± 标准差曲线
  4. 计算组内强度/模量统计量
"""

import os
import logging
import warnings

import numpy as np
import pandas as pd

from filename_parser import scan_directory, SpecimenInfo
from analysis_units import (
    aggregate_analysis_units,
    eligible_measurements,
    statistics_exclusion_mask,
)

log = logging.getLogger("group")


def _detect_flexural_from_path(filepath: str) -> bool:
    """从文件路径检测是否为抗折试验。"""
    path_lower = filepath.lower()
    return "抗折" in path_lower or "bending" in path_lower or "flexural" in path_lower


def load_aligned_curve(filepath: str, flexural: bool | None = None) -> dict | None:
    """
    从处理结果中加载对齐后的曲线。
    抗压: X轴 = strain_pct (%)，Y轴 = stress_MPa
    抗折: X轴 = deform_mm (mm)，Y轴 = stress_MPa
    """
    from process_single import (
        read_data_file,
        fuzzy_rename_columns,
        detect_origin,
        align_data,
        _recalculate_flexural,
    )
    from processing_overrides import get_file_override, apply_processing_override

    if flexural is None:
        flexural = _detect_flexural_from_path(filepath)

    try:
        df = read_data_file(filepath)
        df = fuzzy_rename_columns(df)
        df, _ = apply_processing_override(df, get_file_override(filepath))

        if flexural:
            # 抗折: 用变形(mm)检测原点
            if "deform_mm" in df.columns:
                origin_idx = detect_origin(df, strain_col="deform_mm", threshold=0.001)
            else:
                log.warning("  跳过(无变形列): %s", filepath)
                return None
            df_aligned = align_data(df, origin_idx)
            df_aligned = _recalculate_flexural(df_aligned)
            x_vals = df_aligned["deform_mm_aligned"].values.astype(float)
        else:
            # 抗压: 用应变(%)检测原点
            if "strain_pct" in df.columns:
                origin_idx = detect_origin(df)
            else:
                log.warning("  跳过(无应变列): %s", filepath)
                return None
            df_aligned = align_data(df, origin_idx)
            x_vals = df_aligned["strain_pct_aligned"].values.astype(float)

        stress = df_aligned["stress_MPa_aligned"].values.astype(float)

        return {"x": x_vals, "stress": stress, "flexural": flexural}
    except Exception as e:
        log.warning("  读取失败 %s: %s", os.path.basename(filepath), e)
        return None


def interpolate_to_grid(x, stress, grid):
    """将单条曲线插值到统一的网格。"""
    valid = ~(np.isnan(x) | np.isnan(stress))
    x, stress = x[valid], stress[valid]

    if len(x) < 3:
        return None

    sort_idx = np.argsort(x)
    x, stress = x[sort_idx], stress[sort_idx]

    _, uniq_idx = np.unique(x, return_index=True)
    x, stress = x[uniq_idx], stress[uniq_idx]

    try:
        stress_interp = np.interp(grid, x, stress, left=np.nan, right=np.nan)
        return stress_interp
    except Exception:
        return None


def process_group(group_infos: list, output_dir: str, n_grid: int = 500, exp_type = None, profile = None) -> dict:
    """
    处理单个分组：计算平均曲线 + 统计量。

    Parameters
    ----------
    group_infos : list[SpecimenInfo]
        组内所有 SpecimenInfo。
    output_dir : str
        输出目录。
    n_grid : int
        统一网格点数。

    Returns
    -------
    dict
    """
    gk = group_infos[0].group_key
    label = group_infos[0].group_label
    log.info("处理分组: %s (%s, n=%d)", gk, label, len(group_infos))

    # 检测是否为抗折（取任一文件路径判断）
    if exp_type:
        flexural = bool(
            getattr(exp_type, "is_flexural", False)
            or str(exp_type).lower() in {"flexural", "bending"}
        )
    else:
        flexural = _detect_flexural_from_path(group_infos[0].filepath)

    # summary.csv 是逐文件账本；统计前先过滤显式排除项，再合并为独立试件。
    summary_path = os.path.join(output_dir, "summary.csv")
    filenames_in_group = [info.filename for info in group_infos]
    group_df = pd.DataFrame()
    eligible_group_df = pd.DataFrame()
    analysis_units = pd.DataFrame()
    if os.path.exists(summary_path):
        df_summary = pd.read_csv(summary_path)
        group_df = df_summary[df_summary["filename"].isin(filenames_in_group)].copy()
        eligible_group_df = eligible_measurements(group_df)
        analysis_units = aggregate_analysis_units(group_df)

    eligible_filenames = (
        set(eligible_group_df["filename"].astype(str))
        if not eligible_group_df.empty and "filename" in eligible_group_df.columns
        else set(filenames_in_group)
    )

    # 加载所有有效测量曲线。抗压端部稍后先在试件内平均，再进行组平均。
    curves = []
    all_x = []
    for info in group_infos:
        if info.filename not in eligible_filenames:
            continue
        curve = load_aligned_curve(info.filepath, flexural=flexural)
        if curve is not None and len(curve["x"]) > 5:
            curves.append((info, curve))
            all_x.extend(curve["x"].tolist())

    if not curves:
        log.warning("  分组 %s 无有效曲线", gk)
        return {"group_key": gk, "n": 0, "flexural": flexural}

    # 统一网格（从0到最大值的95%）
    max_x = np.percentile(all_x, 95)
    x_grid = np.linspace(0, max_x, n_grid)

    # 插值所有曲线到统一网格
    stress_grid = []
    stress_by_unit = {}
    for specimen_info, curve in curves:
        s = interpolate_to_grid(curve["x"], curve["stress"], x_grid)
        if s is not None:
            unit_key = f"specimen_{specimen_info.specimen_id}"
            stress_by_unit.setdefault(unit_key, []).append(s)

    for unit_curves in stress_by_unit.values():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            stress_grid.append(np.nanmean(np.asarray(unit_curves), axis=0))

    if not stress_grid:
        log.warning("  分组 %s 插值失败", gk)
        return {"group_key": gk, "n": 0, "flexural": flexural}

    stress_array = np.array(stress_grid)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        stress_mean = np.nanmean(stress_array, axis=0)
        stress_std = (
            np.nanstd(stress_array, axis=0, ddof=1)
            if len(stress_array) > 1
            else np.full_like(stress_mean, np.nan)
        )

    specimens = []
    if not analysis_units.empty:
        for _, row in analysis_units.iterrows():
            specimens.append({
                "label": row.get("analysis_unit_id", "?"),
                "specimen_id": row.get("specimen_id"),
                "source_filenames": row.get("source_filenames", ""),
                "n_measurements": int(row.get("n_measurements", 0)),
                "strength": row.get("strength_MPa"),
                "modulus": row.get("modulus_GPa"),
                "quality_flags": row.get("quality_flags", ""),
            })

    strengths = [s["strength"] for s in specimens if pd.notna(s["strength"])]
    moduli = [s["modulus"] for s in specimens if pd.notna(s["modulus"])]
    quality_flags = sorted({
        flag
        for specimen in specimens
        for flag in str(specimen.get("quality_flags", "")).split("|")
        if flag
    })
    n_excluded = (
        int(statistics_exclusion_mask(group_df).sum()) if not group_df.empty else 0
    )

    # Preserve the stable identity already assigned during directory scanning.
    info = group_infos[0]
    resolved = {
        "age": info.age,
        "condition": info.condition,
        "group_id": info.group_id,
        "mix_id": info.mix_id,
        "group_key": info.group_key,
        "factors": dict(info.factors),
        "label_en": label.removeprefix(f"{info.age}d "),
    }

    result = {
        "group_key": info.group_key,
        "group_label": label,
        "group_label_cn": info.group_label_cn or label,
        "group_label_en": info.group_label_en or label,
        "group_id": info.group_id,
        "mix_id": info.mix_id,
        "factors": dict(info.factors),
        "style": dict(info.style),
        "age": info.age,
        "condition": info.condition,
        "resolved": resolved,
        "n": len(specimens),
        "n_specimens": len(specimens),
        "n_measurements": int(len(eligible_group_df)),
        "n_excluded": n_excluded,
        "statistical_unit": "specimen",
        "quality_flags": quality_flags,
        "flexural": flexural,
        "strength_mean": float(np.mean(strengths)) if strengths else None,
        "strength_std": float(np.std(strengths, ddof=1)) if len(strengths) > 1 else None,
        "modulus_mean": float(np.mean(moduli)) if moduli else None,
        "modulus_std": float(np.std(moduli, ddof=1)) if len(moduli) > 1 else None,
        "x_grid": x_grid,
        "stress_mean": stress_mean,
        "stress_std": stress_std,
        "specimens": specimens,
    }

    unit = "mm" if flexural else "%"
    log.info("  -> %s: 强度=%.3f+-%.3f MPa, 模量=%.3f+-%.3f GPa (n=%d)  [X=%s]",
             gk,
             result["strength_mean"] or 0,
             result["strength_std"] or 0,
             result["modulus_mean"] or 0,
             result["modulus_std"] or 0,
             result["n"], unit)

    return result


def process_all_groups(data_dir: str, output_dir: str, exp_type = None, profile = None) -> list:
    """
    处理所有分组。

    Returns
    -------
    list[dict]: 每个分组的处理结果。
    """
    groups = scan_directory(data_dir, profile=profile)
    results = []

    for gk in sorted(groups.keys()):
        result = process_group(groups[gk], output_dir, exp_type=exp_type, profile=profile)
        results.append(result)

    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 3:
        raise SystemExit("usage: python group_processor.py DATA_DIR OUTPUT_DIR")
    data_dir = sys.argv[1]
    output_dir = sys.argv[2]
    results = process_all_groups(data_dir, output_dir)
