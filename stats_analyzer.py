#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transparent specimen-level descriptive and pairwise statistics."""

from __future__ import annotations

import itertools
import math
import os

import numpy as np
import pandas as pd

from analysis_units import aggregate_analysis_units


T_CRITICAL_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _t_critical(df: int) -> float:
    if df <= 30:
        return T_CRITICAL_975[max(1, df)]
    if df <= 60:
        return 2.000
    if df <= 120:
        return 1.980
    return 1.960


def _group_descriptives(units: pd.DataFrame, metric: str) -> list[dict]:
    if units.empty or "group_key" not in units.columns:
        return []
    rows = []
    for group_key, group in units.groupby("group_key", sort=True):
        values = pd.to_numeric(group[metric], errors="coerce").dropna()
        n = len(values)
        mean = float(values.mean()) if n else float("nan")
        std = float(values.std(ddof=1)) if n > 1 else float("nan")
        margin = _t_critical(n - 1) * std / math.sqrt(n) if n > 1 else float("nan")
        first = group.iloc[0]
        rows.append({
            "group_key": group_key,
            "metric": metric,
            "n_specimens": n,
            "mean": mean,
            "std": std,
            "ci95_lower": mean - margin if n > 1 else float("nan"),
            "ci95_upper": mean + margin if n > 1 else float("nan"),
            "age_days": first.get("age_days"),
            "test_type": first.get("test_type"),
            "group_label_cn": first.get("group_label_cn"),
            "group_label_en": first.get("group_label_en"),
        })
    return rows


def _welch(values_a: np.ndarray, values_b: np.ndarray) -> tuple[float, float, float]:
    n_a, n_b = len(values_a), len(values_b)
    var_a, var_b = np.var(values_a, ddof=1), np.var(values_b, ddof=1)
    denominator = math.sqrt(var_a / n_a + var_b / n_b)
    t_value = (np.mean(values_b) - np.mean(values_a)) / denominator if denominator else 0.0
    numerator = (var_a / n_a + var_b / n_b) ** 2
    denominator_df = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
    degrees = numerator / denominator_df if denominator_df else float("inf")
    try:
        from scipy.stats import t as student_t
        p_value = float(2 * student_t.sf(abs(t_value), degrees))
    except ImportError:
        p_value = float("nan")
    return float(t_value), float(degrees), p_value


def _hedges_g(values_a: np.ndarray, values_b: np.ndarray) -> float:
    n_a, n_b = len(values_a), len(values_b)
    pooled_var = (
        ((n_a - 1) * np.var(values_a, ddof=1) + (n_b - 1) * np.var(values_b, ddof=1))
        / (n_a + n_b - 2)
    )
    if pooled_var <= 0:
        return 0.0
    cohen_d = (np.mean(values_b) - np.mean(values_a)) / math.sqrt(pooled_var)
    correction = 1 - 3 / (4 * (n_a + n_b) - 9)
    return float(cohen_d * correction)


def _pairwise(units: pd.DataFrame, groups_results: list, metric: str) -> list[dict]:
    metadata = {result["group_key"]: result for result in groups_results}
    rows = []
    for group_a, group_b in itertools.combinations(sorted(metadata), 2):
        a, b = metadata[group_a], metadata[group_b]
        if a.get("age") != b.get("age"):
            continue
        factors_a, factors_b = a.get("factors", {}), b.get("factors", {})
        keys = sorted(set(factors_a) | set(factors_b))
        differences = [key for key in keys if factors_a.get(key) != factors_b.get(key)]
        if len(differences) != 1:
            continue
        values_a = pd.to_numeric(
            units.loc[units["group_key"] == group_a, metric], errors="coerce"
        ).dropna().to_numpy(float)
        values_b = pd.to_numeric(
            units.loc[units["group_key"] == group_b, metric], errors="coerce"
        ).dropna().to_numpy(float)
        if len(values_a) < 2 or len(values_b) < 2:
            continue
        t_value, degrees, p_value = _welch(values_a, values_b)
        mean_a, mean_b = float(np.mean(values_a)), float(np.mean(values_b))
        rows.append({
            "metric": metric,
            "age_days": a.get("age"),
            "factor": differences[0],
            "group_a": group_a,
            "group_b": group_b,
            "n_a": len(values_a),
            "n_b": len(values_b),
            "mean_a": mean_a,
            "mean_b": mean_b,
            "mean_difference_b_minus_a": mean_b - mean_a,
            "percent_difference": (mean_b - mean_a) / mean_a * 100 if mean_a else float("nan"),
            "hedges_g": _hedges_g(values_a, values_b),
            "welch_t": t_value,
            "welch_df": degrees,
            "p_value_two_sided": p_value,
            "p_value_status": "available" if pd.notna(p_value) else "scipy_not_installed",
        })
    return rows


def analyze_statistics(
    df_summary: pd.DataFrame,
    groups_results: list,
    tables_dir: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Write enhanced group and pairwise statistics based on specimens."""
    os.makedirs(tables_dir, exist_ok=True)
    units = aggregate_analysis_units(df_summary)
    units.to_csv(os.path.join(tables_dir, "analysis_units.csv"), index=False, encoding="utf-8-sig")

    group_rows = []
    pair_rows = []
    for metric in ("strength_MPa", "modulus_GPa"):
        group_rows.extend(_group_descriptives(units, metric))
        pair_rows.extend(_pairwise(units, groups_results, metric))
    group_df = pd.DataFrame(group_rows)
    pair_df = pd.DataFrame(pair_rows)
    group_df.to_csv(
        os.path.join(tables_dir, "group_statistics_enhanced.csv"), index=False, encoding="utf-8-sig"
    )
    pair_df.to_csv(
        os.path.join(tables_dir, "pairwise_statistics.csv"), index=False, encoding="utf-8-sig"
    )
    return units, group_df, pair_df
