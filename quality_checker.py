#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quality_checker.py — 实验数据质量检查 + 评分

评分维度（每项 0-20 分，5项相加满分 100）：
  1. 数据完整性：文件是否缺失、NaN
  2. 重复性：组内 CV（变异系数）
  3. 一致性：尺寸/面积一致性
  4. 异常检测：峰值异常、离群点
  5. 双源校验：RTF vs Python 一致性
"""

import os
import logging

import numpy as np
import pandas as pd

from analysis_units import aggregate_analysis_units

log = logging.getLogger("qc")


def check_completeness(df_summary: pd.DataFrame) -> dict:
    total = len(df_summary)
    nan_strength = df_summary["strength_MPa"].isna().sum()
    nan_modulus = df_summary["modulus_GPa"].isna().sum()
    errors = (df_summary["status"] != "ok").sum()
    completeness = max(0, 1 - (nan_strength + nan_modulus + errors) / max(total, 1)) * 20
    return {"score": round(completeness, 1), "total_files": total,
            "nan_strength": int(nan_strength), "nan_modulus": int(nan_modulus), "errors": int(errors)}


def check_repeatability(df_summary: pd.DataFrame) -> dict:
    units = aggregate_analysis_units(df_summary)
    if units.empty or "group_key" not in units.columns or "strength_MPa" not in units.columns:
        return {"score": 0, "groups_cv": []}
    groups_cv = []
    cv_values = []
    for gk, grp in units.groupby("group_key"):
        strengths = grp["strength_MPa"].dropna()
        if len(strengths) >= 3:
            cv = np.std(strengths, ddof=1) / np.mean(strengths) * 100
        elif len(strengths) >= 2:
            cv = abs(np.diff(strengths.values)[0]) / np.mean(strengths) * 100
        else:
            cv = None
        groups_cv.append({"group": gk, "n": len(strengths), "cv_pct": round(cv, 2) if cv else None})
        if cv is not None:
            cv_values.append(cv)
    if cv_values:
        mean_cv = np.mean(cv_values)
        score = max(0, min(20, 20 * (1 - mean_cv / 20)))
    else:
        score = 10
    return {"score": round(score, 1), "groups_cv": groups_cv,
            "mean_cv_pct": round(float(np.mean(cv_values)), 2) if cv_values else None}


def check_duplicates(df_summary: pd.DataFrame) -> dict:
    if "duplicate_group_id" not in df_summary.columns:
        return {"checked": False, "duplicate_sets": [], "n_duplicate_sets": 0}
    duplicate_rows = df_summary[
        df_summary["duplicate_group_id"].fillna("").astype(str).ne("")
    ]
    sets = []
    for duplicate_id, group in duplicate_rows.groupby("duplicate_group_id", sort=True):
        sets.append({
            "duplicate_group_id": str(duplicate_id),
            "filenames": group["filename"].astype(str).tolist(),
            "count": int(len(group)),
        })
    return {
        "checked": True,
        "duplicate_sets": sets,
        "n_duplicate_sets": len(sets),
        "n_files_in_duplicate_sets": int(len(duplicate_rows)),
    }


def check_consistency(df_summary: pd.DataFrame) -> dict:
    score = 20
    issues = []
    if "area_mm2" in df_summary.columns:
        areas = df_summary["area_mm2"].dropna()
        if len(areas) > 1 and areas.nunique() > 1:
            issues.append("横截面积不一致")
            score -= 5
    duplicates = check_duplicates(df_summary)
    if duplicates["n_duplicate_sets"]:
        issues.append(
            f"发现 {duplicates['n_duplicate_sets']} 组内容完全相同的原始文件"
        )
        score -= min(10, 5 * duplicates["n_duplicate_sets"])
    return {"score": round(max(score, 0), 1), "issues": issues}


def check_anomalies(df_summary: pd.DataFrame) -> dict:
    units = aggregate_analysis_units(df_summary)
    if units.empty or "strength_MPa" not in units.columns:
        return {"score": 0, "anomalies": []}
    group_column = "group_key" if "group_key" in units.columns else None
    grouped = units.groupby(group_column) if group_column else [("all", units)]
    anomaly_files = []
    group_bounds = []
    for group_key, group in grouped:
        strengths = group["strength_MPa"].dropna()
        if len(strengths) < 4:
            continue
        q1, q3 = strengths.quantile(0.25), strengths.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        anomalies = strengths[(strengths < lower) | (strengths > upper)]
        anomaly_files.extend(units.loc[anomalies.index, "source_filenames"].tolist())
        group_bounds.append({"group": group_key, "q1": round(float(q1), 3),
                             "q3": round(float(q3), 3), "lower": round(float(lower), 3),
                             "upper": round(float(upper), 3)})
    n = len(anomaly_files)
    score = max(0, 20 - n * 5)
    return {"score": round(score, 1), "n_anomalies": n, "anomaly_files": anomaly_files,
            "group_bounds": group_bounds}


def check_rtf_validation(df_summary: pd.DataFrame) -> dict:
    if "strength_diff_pct" not in df_summary.columns:
        return {"score": 10, "checked": False}
    diffs = df_summary["strength_diff_pct"].dropna()
    if len(diffs) == 0:
        return {"score": 10, "checked": False}
    passed = (diffs < 5).sum()
    ratio = passed / len(diffs)
    return {"score": round(ratio * 20, 1), "checked": True, "total_checked": len(diffs),
            "passed": int(passed), "mean_diff_pct": round(float(diffs.mean()), 2)}


def compute_overall_score(scores: dict) -> float:
    """5项满分各20分，直接相加为100分。"""
    total = 0.0
    for key in ["completeness", "repeatability", "consistency", "anomalies", "rtf_validation"]:
        if key in scores and scores[key] is not None:
            total += float(scores[key])
    return round(total, 1)


def get_rating(score: float) -> str:
    if score >= 90: return "Excellent"
    elif score >= 75: return "Good"
    elif score >= 60: return "Fair"
    else: return "Poor"


def run_quality_check(df_summary: pd.DataFrame, output_dir: str = None) -> dict:
    log.info("执行质量检查...")
    scores = {}
    details = {}
    scores["completeness"] = check_completeness(df_summary)["score"]
    details["completeness"] = check_completeness(df_summary)
    repeat = check_repeatability(df_summary)
    scores["repeatability"] = repeat["score"]
    details["repeatability"] = repeat
    scores["consistency"] = check_consistency(df_summary)["score"]
    details["consistency"] = check_consistency(df_summary)
    scores["anomalies"] = check_anomalies(df_summary)["score"]
    details["anomalies"] = check_anomalies(df_summary)
    scores["rtf_validation"] = check_rtf_validation(df_summary)["score"]
    details["rtf_validation"] = check_rtf_validation(df_summary)
    details["duplicates"] = check_duplicates(df_summary)
    overall = compute_overall_score(scores)
    result = {"overall_score": overall, "rating": get_rating(overall), "dimensions": scores, "details": details}
    log.info("  质量评分: %.1f / 100 — %s", overall, result["rating"])
    return result


def print_quality_report(qc_result: dict):
    print(f"\n{'='*55}")
    print(f"{'质量检查报告':^55}")
    print(f"{'='*55}")
    print(f"  综合评分: {qc_result['overall_score']:.1f} / 100  —  {qc_result['rating']}")
    print(f"{'-'*55}")
    for dim, score in qc_result["dimensions"].items():
        bar = "#" * max(1, int(score / 2))
        print(f"  {dim:<20s}: {score:>5.1f} / 20  [{bar}]")
    print(f"{'='*55}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        raise SystemExit("usage: python quality_checker.py SUMMARY_CSV")
    summary_path = sys.argv[1]
    df = pd.read_csv(summary_path)
    result = run_quality_check(df)
    print_quality_report(result)
