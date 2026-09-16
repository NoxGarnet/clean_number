#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiment_type.py — 实验类型检测服务（单次检测，全局共享）"""

import os
import re
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import Union


class ExperimentKind(Enum):
    COMPRESSION = "compression"
    FLEXURAL = "flexural"
    UNKNOWN = "unknown"

    @property
    def is_flexural(self) -> bool:
        return self == ExperimentKind.FLEXURAL

    @property
    def is_compression(self) -> bool:
        return self == ExperimentKind.COMPRESSION


@dataclass
class ExperimentType:
    """实验类型数据类，封装检测结果和标签。"""
    kind: ExperimentKind

    @property
    def is_flexural(self) -> bool:
        return self.kind == ExperimentKind.FLEXURAL

    @property
    def is_compression(self) -> bool:
        return self.kind == ExperimentKind.COMPRESSION

    @property
    def label_cn(self) -> str:
        m = {ExperimentKind.COMPRESSION: "抗压试验", ExperimentKind.FLEXURAL: "抗折试验", ExperimentKind.UNKNOWN: "未知试验"}
        return m.get(self.kind, "未知试验")

    @property
    def label_en(self) -> str:
        m = {ExperimentKind.COMPRESSION: "Compression Test", ExperimentKind.FLEXURAL: "Flexural Test", ExperimentKind.UNKNOWN: "Unknown Test"}
        return m.get(self.kind, "Unknown Test")

    @property
    def strength_label_cn(self) -> str:
        m = {ExperimentKind.COMPRESSION: "抗压强度", ExperimentKind.FLEXURAL: "抗折强度", ExperimentKind.UNKNOWN: "强度"}
        return m.get(self.kind, "强度")

    @property
    def strength_label_en(self) -> str:
        m = {ExperimentKind.COMPRESSION: "Compressive Strength", ExperimentKind.FLEXURAL: "Flexural Strength", ExperimentKind.UNKNOWN: "Strength"}
        return m.get(self.kind, "Strength")

    @property
    def x_axis_label(self) -> str:
        return "Displacement (mm)" if self.is_flexural else "Strain (%)"

    @property
    def y_axis_label(self) -> str:
        return "Stress (MPa)"

    @property
    def figure_title(self) -> str:
        return "Flexural Stress-Displacement Curves" if self.is_flexural else "Compressive Stress-Strain Curves"

    @property
    def curve_suffix(self) -> str:
        return "_flexural" if self.is_flexural else ""

    def __repr__(self) -> str:
        return f"ExperimentType({self.kind.value})"


def detect(path: Union[Path, str], explicit_kind: str | None = None) -> ExperimentType:
    """Detect a supported test type without silently defaulting to compression."""
    if explicit_kind:
        value = str(explicit_kind).strip().lower()
        if value in {"compression", "compressive"}:
            return COMPRESSION
        if value in {"flexural", "bending"}:
            return FLEXURAL
        raise ValueError(f"Unsupported test kind: {explicit_kind}")

    path = Path(path).resolve()
    path_str = str(path).lower()

    # 策略1: 路径关键词
    if any(kw in path_str for kw in ["抗折", "bending", "flexural"]):
        return ExperimentType(ExperimentKind.FLEXURAL)
    if any(kw in path_str for kw in ["抗压", "compression", "compressive"]):
        return ExperimentType(ExperimentKind.COMPRESSION)

    # 策略2: RTF文件内容检测
    if path.is_dir():
        for f in sorted(os.listdir(path)):
            if f.lower().endswith(".rtf"):
                fp = os.path.join(path, f)
                if os.path.isfile(fp):
                    return _detect_from_rtf(fp)

    return UNKNOWN


def _detect_from_rtf(rtf_path: str) -> ExperimentType:
    try:
        with open(rtf_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return UNKNOWN

    if "抗折" in text or "bending" in text.lower() or "flexural" in text.lower():
        return ExperimentType(ExperimentKind.FLEXURAL)
    return UNKNOWN


# 便捷常量
COMPRESSION = ExperimentType(ExperimentKind.COMPRESSION)
FLEXURAL = ExperimentType(ExperimentKind.FLEXURAL)
UNKNOWN = ExperimentType(ExperimentKind.UNKNOWN)
