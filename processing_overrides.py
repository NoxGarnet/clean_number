#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project-level, auditable overrides for exceptional raw test files."""

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from path_utils import _find_project_root


CONFIG_FILENAME = "processing_overrides.yaml"


def _normalise_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").casefold()


@lru_cache(maxsize=16)
def _load_project_config(project_root_str: str) -> dict:
    config_path = Path(project_root_str) / CONFIG_FILENAME
    if not config_path.is_file():
        return {}

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    files = data.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"{config_path}: 'files' 必须是映射。")
    return files


def get_file_override(filepath: str) -> dict | None:
    """Load the override matching ``filepath`` relative to its project root."""
    file_path = Path(filepath).resolve()
    project_root = _find_project_root(str(file_path))
    files = _load_project_config(str(project_root.resolve()))
    target = _normalise_path(file_path)

    for relative_path, override in files.items():
        candidate = _normalise_path(project_root / str(relative_path))
        if candidate == target:
            if not isinstance(override, dict):
                raise ValueError(f"{CONFIG_FILENAME}: {relative_path} 的覆盖规则必须是映射。")
            return override
    return None


def apply_processing_override(
    df: pd.DataFrame,
    override: dict | None,
) -> tuple[pd.DataFrame, dict]:
    """Apply an inclusive cutoff without modifying the source file.

    When both row and time are supplied they must identify the same record.
    This fail-closed check prevents a stale override from silently truncating a
    changed source file at the wrong point.
    """
    metadata = {
        "override_applied": False,
        "raw_data_points": len(df),
        "cutoff_row": None,
        "cutoff_time_s": None,
        "reason": None,
    }
    if not override or not override.get("enabled", True):
        return df, metadata

    cutoff = override.get("cutoff")
    if cutoff is None and override.get("exclude_from_statistics", False):
        # Exclusion-only rules leave the processed curve untouched.  The
        # batch ledger records the exclusion and group statistics filter it.
        metadata["reason"] = override.get("exclusion_reason") or override.get("reason")
        return df, metadata
    if cutoff is None:
        raise ValueError("处理覆盖规则必须提供 cutoff，或明确 exclude_from_statistics。")
    if not isinstance(cutoff, dict):
        raise ValueError("处理覆盖规则的 'cutoff' 必须是映射。")

    row = cutoff.get("row_inclusive")
    time_s = cutoff.get("time_s_inclusive")
    if row is None and time_s is None:
        raise ValueError("处理覆盖规则必须提供 row_inclusive 或 time_s_inclusive。")

    end_positions = []
    if row is not None:
        row = int(row)
        if row < 0 or row >= len(df):
            raise ValueError(f"覆盖截止行 {row} 超出数据范围 0..{len(df) - 1}。")
        end_positions.append(row)

    if time_s is not None:
        if "time_s" not in df.columns:
            raise ValueError("覆盖规则指定了 time_s_inclusive，但数据缺少 time_s 列。")
        time_s = float(time_s)
        times = pd.to_numeric(df["time_s"], errors="coerce")
        matches = times.index[times <= time_s]
        if len(matches) == 0:
            raise ValueError(f"没有数据点满足 time_s <= {time_s}。")
        time_position = int(df.index.get_indexer([matches[-1]])[0])
        end_positions.append(time_position)

    if row is not None and time_s is not None:
        row_time = float(pd.to_numeric(df.iloc[row]["time_s"], errors="coerce"))
        if abs(row_time - time_s) > 1e-6:
            raise ValueError(
                f"覆盖规则不一致：第 {row} 行时间为 {row_time} s，"
                f"配置时间为 {time_s} s。"
            )

    end_position = min(end_positions)
    trimmed = df.iloc[: end_position + 1].copy()
    metadata.update({
        "override_applied": True,
        "cutoff_row": end_position,
        "cutoff_time_s": (
            float(trimmed["time_s"].iloc[-1]) if "time_s" in trimmed.columns else time_s
        ),
        "reason": override.get("reason"),
    })
    return trimmed, metadata
