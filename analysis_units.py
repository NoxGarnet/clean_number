#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build independent experimental units from per-file pipeline results.

``summary.csv`` remains the immutable per-file processing ledger.  Statistical
analysis uses this module to collapse repeated measurements of the same
specimen (for example the two compression ends) into one independent unit.
"""

from __future__ import annotations

import math

import pandas as pd


IDENTITY_COLUMNS = [
    "group_label",
    "group_label_cn",
    "group_label_en",
    "group_id",
    "mix_id",
    "age_days",
    "condition",
    "test_type",
]


def _bool_series(df: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=bool)
    values = df[column]
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(default)
    truthy = {"true", "1", "yes", "y", "是"}
    return values.fillna(default).map(
        lambda value: str(value).strip().casefold() in truthy
    )


def statistics_exclusion_mask(df_summary: pd.DataFrame) -> pd.Series:
    """Return rows explicitly excluded from group-level statistics."""
    return _bool_series(df_summary, "exclude_from_statistics", default=False)


def eligible_measurements(df_summary: pd.DataFrame) -> pd.DataFrame:
    """Return successful, non-excluded per-file measurements."""
    if df_summary.empty:
        return df_summary.copy()
    status = (
        df_summary["status"].fillna("").astype(str).str.casefold().eq("ok")
        if "status" in df_summary.columns
        else pd.Series(True, index=df_summary.index)
    )
    return df_summary.loc[status & ~statistics_exclusion_mask(df_summary)].copy()


def _join_unique(values) -> str:
    items = []
    for value in values:
        if pd.isna(value):
            continue
        for item in str(value).split("|"):
            item = item.strip()
            if item and item not in items:
                items.append(item)
    return "|".join(items)


def _unit_identifier(row: pd.Series) -> str:
    specimen_id = row.get("specimen_id")
    if specimen_id is not None and not pd.isna(specimen_id):
        try:
            value = float(specimen_id)
            specimen_text = str(int(value)) if math.isfinite(value) and value.is_integer() else str(specimen_id)
        except (TypeError, ValueError):
            specimen_text = str(specimen_id)
        return f"specimen_{specimen_text}"
    return f"file_{row.get('filename', row.name)}"


def aggregate_analysis_units(df_summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-file results into independent specimen-level records.

    All valid measurements sharing ``group_key`` and ``specimen_id`` are
    averaged.  Flexural data normally has one file per specimen, while
    compression data commonly has two end measurements per specimen.
    """
    measurements = eligible_measurements(df_summary)
    if measurements.empty:
        return pd.DataFrame()
    if "group_key" not in measurements.columns:
        raise ValueError("summary 数据缺少 group_key，无法建立独立试件统计。")

    measurements["analysis_unit_id"] = measurements.apply(_unit_identifier, axis=1)
    factor_columns = sorted(c for c in measurements.columns if c.startswith("factor_"))
    records = []

    for (group_key, unit_id), group in measurements.groupby(
        ["group_key", "analysis_unit_id"], sort=True, dropna=False
    ):
        first = group.iloc[0]
        filenames = [str(value) for value in group.get("filename", pd.Series(dtype=str)).dropna()]
        record = {
            "group_key": group_key,
            "analysis_unit_id": unit_id,
            "specimen_id": first.get("specimen_id"),
            "source_filenames": "|".join(filenames),
            "n_measurements": int(len(group)),
            "strength_MPa": pd.to_numeric(group.get("strength_MPa"), errors="coerce").mean(),
            "modulus_GPa": pd.to_numeric(group.get("modulus_GPa"), errors="coerce").mean(),
            "quality_flags": _join_unique(group.get("quality_flags", pd.Series(dtype=str))),
            "contains_duplicate_content": bool(_bool_series(group, "is_duplicate_content").any()),
            "contains_processing_override": bool(_bool_series(group, "override_applied").any()),
        }
        for column in IDENTITY_COLUMNS + factor_columns:
            if column in group.columns:
                record[column] = first.get(column)
        records.append(record)

    result = pd.DataFrame(records)
    if not result.empty:
        result = result.sort_values(
            [column for column in ["test_type", "age_days", "group_key", "specimen_id"] if column in result.columns],
            kind="stable",
        ).reset_index(drop=True)
    return result
